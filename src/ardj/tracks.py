# encoding=utf-8

"""Track management for ardj.

Contains functions that interact with the database in order to modify or query
tracks.
"""

import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import traceback
import urllib

import ardj.database
import ardj.jabber
import ardj.jamendo
import ardj.listeners
import ardj.log
import ardj.podcast
import ardj.replaygain
import ardj.settings
import ardj.scrobbler
import ardj.tags
import ardj.util

from ardj import is_dry_run, is_verbose
from ardj.database import Track as Track2
from ardj.users import resolve_alias
from ardj.log import log_info


KARMA_TTL = 30.0
STICKY_LABEL_FILE_NAME = "~/.ardj-sticky.json"


class Forbidden(Exception):
    pass


class Playlist(dict):
    def add_ts(self, stats):
        self['last_played'] = 0
        if self['name'] in stats:
            self['last_played'] = stats[self['name']]
        return self

    def match_track(self, track):
        if not isinstance(track, dict):
            raise TypeError
        if not self.match_labels(track.get('labels')):
            return False
        if not self.match_repeat(track.get('count', 0)):
            return False
        if not self.match_weight(track.get('weight', 1.0)):
            return False
        return True

    def match_weight(self, other):
        if '-' not in self.get('weight', ''):
            return True
        min, max = [float(x) for x in self.get('weight').split('-', 1)]
        if other >= min and other <= max:
            return True
        return False

    def match_repeat(self, other):
        if 'repeat' not in self or not other:
            return True
        return other < self['repeat']

    def match_labels(self, other):
        """Checks whether labels apply to this playlist."""
        if not other:
            return False

        plabels = self.get('labels', [self.get('name')])
        success = False

        for plabel in plabels:
            if plabel.startswith('-'):
                if plabel[1:] in other:
                    return False
            if plabel.startswith('+'):
                if plabel[1:] not in other:
                    return False
            elif plabel in other:
                success = True

        return success

    def is_active(self, timestamp=None):
        """Checks whether the playlist can be used right now."""
        now = time.localtime(timestamp)

        now_ts = time.mktime(now)
        now_day = int(time.strftime('%w', now))
        now_hour = int(time.strftime('%H', now))
        now_minutes = int(time.strftime('%M', now))

        if 'delay' in self and self['delay'] * 60 + self['last_played'] >= now_ts:
            return False
        if 'hours' in self and now_hour not in self.get_hours():
            return False
        if 'days' in self and now_day not in self.get_days():
            return False
        if 'minutes' in self and now_minutes not in self.get_minutes():
            return False
        return True

    def get_days(self):
        return ardj.util.expand(self['days'])

    def get_hours(self):
        return ardj.util.expand(self['hours'])

    def get_minutes(self):
        return ardj.util.expand(self['minutes'])

    @classmethod
    def get_active(cls, timestamp=None):
        return [p for p in cls.get_all() if p.is_active(timestamp)]

    @classmethod
    def get_all(cls):
        """Returns information about all known playlists.  Information from
        playlists.yaml is complemented by the last_played column of the
        `playlists' table."""
        stats = dict(ardj.database.fetch('SELECT name, last_played FROM playlists WHERE name IS NOT NULL AND last_played IS NOT NULL'))
        return [cls(p).add_ts(stats) for p in ardj.settings.load().get_playlists()]

    @classmethod
    def touch_by_track(cls, track_id):
        """Finds playlists that contain this track and updates their last_played
        property, so that they could be delayed properly."""
        track = get_track_by_id(track_id)
        ts = int(time.time())

        for playlist in cls.get_all():
            name = playlist.get('name')
            if name and playlist.match_track(track):
                logging.debug('Track %u touches playlist "%s".' % (track_id, name.encode("utf-8")))
                rowcount = ardj.database.execute('UPDATE playlists SET last_played = ? WHERE name = ?', (ts, name, ))
                if rowcount == 0:
                    ardj.database.execute('INSERT INTO playlists (name, last_played) VALUES (?, ?)', (name, ts, ))


class Track(dict):
    # TODO: move to ardj.database after sawing down StORM.

    table_name = "tracks"
    fields = ("id", "owner", "filename", "artist", "title", "length", "weight", "count", "last_played", "real_weight", "image", "download")
    key_name = "id"

    def get_labels(self):
        if "labels" not in self:
            rows = ardj.database.fetch("SELECT label FROM labels WHERE track_id = ?", (self["id"], ))
            self["labels"] = sorted(list(set([row[0] for row in rows])))
        return self["labels"]

    def get_artist_url(self):
        if "lastfm:noartist" in self.get_labels():
            return None
        q = lambda v: urllib.quote(v.encode("utf-8"))
        return "http://www.last.fm/music/%s" % q(self["artist"])

    def get_track_url(self):
        if "lastfm:notfound" in self.get_labels():
            return None
        q = lambda v: urllib.quote(v.encode("utf-8"))
        return "http://www.last.fm/music/%s/_/%s" % (q(self["artist"]), q(self["title"]))

    @classmethod
    def get_by_id(cls, track_id):
        if not track_id:
            return None
        sql = "SELECT %s FROM %s WHERE %s = ?" % (", ".join(cls.fields), cls.table_name, cls.key_name)
        row = ardj.database.fetchone(sql, (int(track_id), ))
        if not row:
            return None
        return Track([(cls.fields[k], v) for k, v in enumerate(row)])

    @classmethod
    def get_last(cls):
        sql = "SELECT %s FROM %s ORDER BY last_played DESC LIMIT 1" % (", ".join(cls.fields), cls.table_name)
        row = ardj.database.fetchone(sql)
        return Track([(cls.fields[k], v) for k, v in enumerate(row)])

    def get_last_vote(self, sender):
        votes = ardj.database.fetchone("SELECT vote FROM votes WHERE track_id = ? AND email = ? ORDER BY id DESC", (self["id"], sender, ))
        return votes[0] if votes else 0

    def refresh_tags(self, filepath):
        tags = ardj.tags.get(filepath)

        write = False

        duration = tags.get("length", 0)
        if duration != self["length"]:
            log_info(u"Updating track {0} duration to {1}.",
                self["id"], duration)
            self["duration"] = duration
            write = True

        artist = tags.get("artist", "Unknown Artist")
        if artist != self["artist"]:
            log_info(u"Updating track {0} artist to {1}.",
                self["id"], artist)
            self["artist"] = artist
            write = True

        title = tags.get("title", "Untitled")
        if title != self["title"]:
            log_info(u"Updating track {0} title to {1}.",
                self["id"], title)
            self["title"] = title
            write = True

        if write:
            ardj.database.execute("UPDATE tracks SET artist = ?, title = ?, length = ? WHERE id = ?", (artist, title, duration, self["id"]))

    def write_tags(self):
        tags = ardj.tags.get(self.get_filepath())

        new_tags = {}

        if tags["artist"] != self["artist"]:
            new_tags["artist"] = self["artist"]

        if tags["title"] != self["title"]:
            new_tags["title"] = self["title"]

        labels = self.get_labels()
        if tags.get("labels") != labels:
            new_tags["labels"] = labels

        if new_tags:
            log_info("Writing new tags to {0}.", self["filename"])
            ardj.tags.set(self.get_filepath(), new_tags)

    def get_filepath(self):
        return get_real_track_path(self["filename"])


class Sticky(dict):
    def __init__(self):
        self.fn = os.path.expanduser(STICKY_LABEL_FILE_NAME)
        if os.path.exists(self.fn):
            with open(self.fn, "rb") as f:
                self.update(json.loads(f.read()))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.flush()

    def flush(self):
        with open(self.fn, "wb") as f:
            f.write(json.dumps(dict(self)))
            logging.debug("Wrote %s" % self.fn)

    def __getitem__(self, k):
        return self.get(k)


def get_real_track_path(filename):
    return os.path.join(ardj.settings.get_music_dir(), filename)


def get_track_by_id(track_id, sender=None):
    """Returns track description as a dictionary.

    If the track does not exist, returns None.  Extended properties,
    such as labels, are also returned.

    Arguments:
    track_id -- identified the track to return.
    cur -- unused.
    """
    track = Track.get_by_id(track_id)
    if track is None:
        return None

    track["labels"] = track.get_labels()
    if track.get('filename'):
        track['filepath'] = get_real_track_path(track['filename'])

    track["track_url"] = track.get_track_url()
    track["artist_url"] = track.get_artist_url()

    if sender is not None:
        track["bookmark"] = "bm:%s" % sender in track["labels"]
        track["vote"] = track.get_last_vote(sender)
    else:
        track["bookmark"] = False

    track["labels"] = [l for l in track["labels"] if not l.startswith("bm:")]

    return track


def get_last_track_id():
    """Returns id of the last played track.

    If the database is empty, returns None, otherwise an integer.

    Keyword arguments:
    cur -- database cursor, created if None.
    """
    row = ardj.database.fetchone("SELECT id FROM tracks ORDER BY last_played DESC LIMIT 1")
    if row:
        return row[0]


def get_last_track():
    """Returns the full description of the last played track.

    Calls get_track_by_id(get_last_track_id()).
    """
    return get_track_by_id(get_last_track_id())


def identify(track_id, unknown='an unknown track'):
    track = get_track_by_id(track_id)
    if not track:
        return unknown
    return u'«%s» by %s [%u]' % (track.get('title', 'untitled'), track.get('artist', 'unknown artist'), track_id)


def queue(track_id, owner=None):
    """Adds the track to queue."""
    return ardj.database.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track_id, (owner or 'ardj').lower(), ))


def get_queue():
    rows = ardj.database.fetch("SELECT track_id FROM queue ORDER BY id")
    return [get_track_by_id(row[0]) for row in rows]


def find_ids(pattern, sender=None, limit=None):
    search_order = 'weight DESC'
    search_args = []
    search_labels = []
    search_ids = []

    args = [a for a in pattern.split(' ') if a.strip()]
    for arg in args:
        if arg == '-r':
            search_order = 'RANDOM()'
        elif arg == '-l':
            search_order = 'id DESC'
        elif arg == '-f':
            search_order = 'id'
        elif arg == '-c':
            search_order = 'count DESC'
        elif arg == '-c-':
            search_order = 'count ASC'
        elif arg == '-b' and sender is not None:
            search_labels.append('bm:' + sender.lower())
            search_ids = None
        elif arg.isdigit():
            if search_ids is not None:
                search_ids.append(arg)
        elif arg.startswith('#'):
            search_labels.append(arg[1:])
            search_ids = None
        else:
            search_args.append(arg)
            search_ids = None

    if search_ids:
        return [int(x) for x in search_ids]

    pattern = u' '.join(search_args)

    params = []
    where = []

    if search_labels:
        _add_label_filter(search_labels, where, params)

    if search_args:
        like = u' '.join(search_args)
        where.append('(ULIKE(artist, ?) OR ULIKE(title, ?))')
        params.append(like)
        params.append(like)

    if not params:
        return []

    sql = 'SELECT id FROM tracks WHERE weight > 0 AND %s ORDER BY %s' % (' AND '.join(where), search_order)
    if limit is not None:
        sql += ' LIMIT %u' % limit
    rows = ardj.database.fetch(sql, params)
    return [row[0] for row in rows]


def _add_label_filter(labels, where, params):
    """Adds condition for filtering tracks by labels."""
    other_labels = []

    for label in labels:
        if label.startswith("+"):
            where.append('id IN (SELECT track_id FROM labels WHERE label = ?)')
            params.append(label[1:])
        elif label.startswith("-"):
            where.append('id NOT IN (SELECT track_id FROM labels WHERE label = ?)')
            params.append(label[1:])
        else:
            other_labels.append(label)

    if other_labels:
        sql = "id IN (SELECT track_id FROM labels WHERE label IN (%s))" % ", ".join(['?'] * len(other_labels))
        where.append(sql)
        params.extend(other_labels)


def add_labels(track_id, labels, owner=None):
    if labels:
        for label in labels:
            if label.startswith('-'):
                ardj.database.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('-'), ))
            elif ardj.database.fetch('SELECT 1 FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('+'), )):
                pass
            else:
                ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label.lstrip('+'), owner or 'ardj', ))

    track = Track.get_by_id(int(track_id))
    track.write_tags()

    return track.get_labels()


def update_track(properties):
    """Updates valid track attributes.

    Loads the track specified in properties['id'], then updates its known
    fields with the rest of the properties dictionary, then saves the
    track.  If there's the "labels" key in properties (must be a list),
    labels are added (old are preserved) to the `labels` table.

    If there's not fields to update, a message is written to the debug log.
    """
    if not isinstance(properties, dict):
        raise Exception('Track properties must be passed as a dictionary.')
    if 'id' not in properties:
        raise Exception('Track properties have no id.')

    sql = []
    params = []
    for k in properties:
        if k in ('filename', 'artist', 'title', 'length', 'weight', 'count', 'last_played', 'owner', 'real_weight', 'download', 'image'):
            sql.append(k + ' = ?')
            params.append(properties[k])

    if not sql:
        logging.debug('No fields to update.')
    else:
        params.append(properties['id'])
        sql = 'UPDATE tracks SET ' + ', '.join(sql) + ' WHERE id = ?'
        ardj.database.execute(sql, tuple(params))

    if properties.get('labels'):
        add_labels(properties['id'], properties['labels'], owner=properties.get('owner'))

    track = Track.get_by_id(int(properties["id"]))
    track.write_tags()


def purge():
    """Deletes tracks with zero weight.

    Removes files, track entries are left in the database to prevent reloading
    by podcaster etc.
    """
    music_dir = ardj.settings.get_music_dir()

    # mark tracks that no longer have files
    for track_id, filename in ardj.database.fetch('SELECT id, filename FROM tracks WHERE weight > 0 AND filename IS NOT NULL'):
        abs_filename = os.path.join(music_dir, filename)
        if not os.path.exists(abs_filename):
            logging.warning('Track %u vanished (%s), deleting.' % (track_id, filename))
            ardj.database.execute('UPDATE tracks SET weight = 0 WHERE id = ?', (track_id, ))

    for track_id, filename in ardj.database.fetch('SELECT id, filename FROM tracks WHERE weight = 0 AND filename IS NOT NULL'):
        abs_filename = os.path.join(music_dir, filename)
        if os.path.exists(abs_filename):
            os.unlink(abs_filename)
            logging.info('Deleted track %u (%s) from file system.' % (track_id, filename))

    ardj.database.execute('UPDATE tracks SET filename = NULL WHERE weight = 0')
    # ardj.database.Open().purge()


def get_urgent():
    """Returns current playlist preferences."""
    data = ardj.database.fetch('SELECT labels FROM urgent_playlists WHERE expires > ? ORDER BY expires', (int(time.time()), ))
    if data:
        return re.split('[,\s]+', data[0][0])
    return None


def extract_duration(play_args):
    duration = 60

    new_args = []
    for arg in re.split("\s+", play_args):
        if arg.startswith("--time="):
            duration = int(arg[7:])
        else:
            new_args.append(arg)
    return duration, u" ".join(new_args)


def set_urgent(args):
    """Sets the music filter.

    Sets music filter to be used for picking random tracks.  If set, only
    matching tracks will be played, regardless of playlists.yaml.  Labels
    must be specified as a string, using spaces or commas as separators.
    Use "all" to reset.
    """
    ardj.database.execute('DELETE FROM urgent_playlists')

    if args == 'all':
        ardj.jabber.chat_say(u"Returning to normal playlists.")
    else:
        duration, args = extract_duration(args)
        expires = time.time() + duration * 60
        ardj.database.execute('INSERT INTO urgent_playlists (labels, expires) VALUES (?, ?)', (args, int(expires), ))
        ardj.jabber.chat_say(u"Playlist for next %u minutes: %s." % (duration, args))


def add_vote(track_id, email, vote, update_karma=False):
    """Adds a vote for/against a track.

    The process is: 1) add a record to the votes table, 2) update email's
    record in the karma table, 3) update weight for all tracks email voted
    for/against.

    Votes other than +1 and -1 are skipped.

    Returns track's current weight.
    """
    email = email.lower()

    if not ardj.settings.get("enable_voting", True):
        raise Forbidden("Voting disabled by the admins.")

    # Normalize the vote.
    if vote > 0:
        vote = 1
    elif vote < 0:
        vote = -1

    # Resolve aliases.
    email = resolve_alias(email)

    row = ardj.database.fetchone("SELECT last_played, weight FROM tracks WHERE id = ?", (track_id, ))
    if row is None:
        return None

    last_played, current_weight = row
    if not last_played:
        raise Exception('This track was never played.')
    elif current_weight <= 0:
        raise Exception("Can't vote for deleted tracks.")

    vote_count = ardj.database.fetchone("SELECT COUNT(*) FROM votes WHERE track_id = ? "
        "AND email = ? AND vote = ? AND ts >= ?", (track_id, email, vote,
        last_played, ))[0]

    ardj.database.execute('INSERT INTO votes (track_id, email, vote, ts) '
        'VALUES (?, ?, ?, ?)', (track_id, email, vote, int(time.time()), ))

    # Update current track weight.
    if not vote_count:
        current_weight = max(current_weight + vote * 0.25, 0.01)
        ardj.database.execute('UPDATE tracks SET weight = ? WHERE id = ?', (current_weight, track_id, ))

        update_real_track_weight(track_id)

    real_weight = ardj.database.fetchone('SELECT weight FROM tracks WHERE id = ?',
        (track_id, ))[0]
    return real_weight


def get_vote(track_id, email):
    return get_track_votes(track_id).get(email.lower(), 0)


def get_track_votes(track_id):
    results = {}
    for email, vote in ardj.database.fetch("SELECT email, vote FROM votes WHERE track_id = ?", (track_id, )):
        results[email.lower()] = vote
    return results


def add_file(filename, add_labels=None, owner=None, quiet=False, artist=None, title=None, dlink=None):
    """Adds the file to the database.

    Returns track id.
    """
    if not os.path.exists(filename):
        raise Exception('File not found: %s' % filename)

    if not quiet:
        logging.info('Adding from %s' % filename)
    ardj.replaygain.update(filename)

    tags = ardj.tags.get(str(filename)) or {}
    duration = tags.get('length', 0)
    labels = tags.get('labels', [])

    if artist is None:
        artist = tags.get('artist', 'Unknown Artist')
    if title is None:
        title = tags.get('title', 'Untitled')

    if add_labels and not labels:
        labels = add_labels

    rel_path = os.path.relpath(filename,
        ardj.settings.get_music_dir())

    track_id = ardj.database.execute('INSERT INTO tracks (artist, title, filename, length, last_played, owner, weight, real_weight, count, download) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 0, ?)', (artist, title, rel_path, duration, 0, owner or 'ardj', dlink, ))
    for label in labels:
        ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label, (owner or 'ardj').lower(), ))
    return track_id


def get_track_id_from_queue():
    """Returns a track from the top of the queue.

    If the queue is empty or there's no valid track in it, returns None.
    """
    row = ardj.database.fetchone('SELECT id, track_id FROM queue ORDER BY id LIMIT 1')
    if row:
        ardj.database.execute('DELETE FROM queue WHERE id = ?', (row[0], ))
        if not row[1]:
            return None
        track = get_track_by_id(row[1])
        if track is None:
            return None
        if not track.get('filename'):
            return None
        return row[1]


def get_random_track_id_from_playlist(playlist, skip_artists):
    sql = 'SELECT id, weight, artist, count, last_played FROM tracks WHERE weight > 0 AND artist IS NOT NULL AND filename IS NOT NULL'
    params = []

    labels = list(playlist.get('labels', [playlist.get('name', 'music')]))
    labels.extend(get_sticky_label(playlist))

    sql, params = add_labels_filter(sql, params, labels)

    repeat_count = playlist.get('repeat')
    if repeat_count:
        sql += ' AND count < ?'
        params.append(int(repeat_count))

    if skip_artists:
        skip_count = int(playlist.get("artist_delay", playlist.get("history", "10")))
        skip_artists = skip_artists[:skip_count]
        if skip_artists:
            sql += ' AND artist NOT IN (%s)' % ', '.join(['?'] * len(skip_artists))
            params += skip_artists

    weight = playlist.get('weight', '')
    if '-' in weight:
        parts = weight.split('-', 1)
        sql += ' AND weight >= ? AND weight <= ?'
        params.append(float(parts[0]))
        params.append(float(parts[1]))

    delay = playlist.get('track_delay')
    if delay:
        sql += ' AND (last_played IS NULL OR last_played <= ?)'
        params.append(int(time.time()) - int(delay) * 60)

    ardj.database.Open().debug(sql, params)
    track_id = get_random_row(ardj.database.fetch(sql, tuple(params)), playlist.get("strategy", "default"))

    if track_id is not None:
        update_sticky_label(track_id, playlist)
        if playlist.get('preroll'):
            track_id = add_preroll(track_id, playlist.get('preroll'))

    return track_id


def update_sticky_label(track_id, playlist):
    """Updates active sticky labels.  If the playlist has no sticky labels,
    they are reset.  If track has none, they are reset.  If track has some, a
    random one is stored."""
    with Sticky() as sticky:
        # Save the new playlist name.  If it changed -- remove previous label.
        if sticky["playlist"] != playlist.get("name", "unnamed"):
            if sticky["label"] is not None:
                logging.info("Playlist changed to %s, dropping sticky label \"%s\"." % (playlist["name"], sticky["label"]))
                sticky["label"] = None

        sticky["playlist"] = playlist.get("name", "unnamed")

        # There is a sticky label already, nothing to do.
        if sticky["label"]:
            logging.info("Using sticky label %s" % sticky["label"].encode("utf-8"))
            return

        # This playlist has no sticky labels, nothing to do.
        if not playlist.get("sticky_labels"):
            logging.debug("Sticky: playlist %s has no sticky_labels." % sticky["playlist"])
            return

        # Find intersecting labels.
        track = Track.get_by_id(track_id)
        if track is None:
            logging.debug("Sticky: track %s not found -- no labels to pick from." % track_id)
            return

        # No intersection, nothing to do.
        labels = list(set(track.get_labels()) & set(playlist["sticky_labels"]))
        if not labels:
            logging.debug("Sticky: track %u has no labels to stick to playlist %s." % (track["id"], sticky["playlist"]))
            return

        # Store the new sticky label.
        sticky["label"] = random.choice(labels)
        logging.info("New sticky label: %s" % sticky["label"].encode("utf-8"))


def get_sticky_label(playlist):
    """
    Returns sticky labels that apply to this playlist.
    """
    with Sticky() as sticky:
        # Playlist changed, ignore previously used sticky labels.
        if playlist.get("name", "unnamed") != sticky["playlist"]:
            if sticky["label"]:
                logging.debug("Sticky: playlist changed to %s, forgetting old label %s." % (playlist.get("name"), sticky["label"]))
            return []

        if not sticky["label"]:
            return []

        logging.debug("Sticky: forcing label %s" % sticky["label"])
        return [u"+" + sticky["label"]]


def add_labels_filter(sql, params, labels):
    either = [l for l in labels if not l.startswith('-') and not l.startswith('+')]
    neither = [l[1:] for l in labels if l.startswith('-')]
    every = [l[1:] for l in labels if l.startswith('+')]

    if either:
        sql += ' AND id IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(either))
        params += either

    if neither:
        sql += ' AND id NOT IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(neither))
        params += neither

    if every:
        for label in every:
            sql += ' AND id IN (SELECT track_id FROM labels WHERE label = ?)'
            params.append(label)

    return sql, params


def get_random_row(rows, strategy=None):
    if not rows:
        return None

    if strategy == "fresh":
        rows.sort(key=lambda row: row[3])
        row = random.choice(rows[:5])
        track_id = row[0]

    elif strategy == "oldest":
        rows.sort(key=lambda row: row[4])
        row = rows[0]
        track_id = row[0]

    else:
        track_id = get_random_row_default(rows)

    logging.debug("Picked track %s using strategy '%s'." % (track_id, strategy))
    return track_id


def get_random_row_default(rows):
    """Picks a random row using the default strategy.

    First divides track weights by the number of tracks that the artist has,
    then picks a random track based on the updated weight.
    """
    ID_COL, WEIGHT_COL, NAME_COL = 0, 1, 2

    artist_counts = {}
    for row in rows:
        name = row[NAME_COL].lower()
        if name not in artist_counts:
            artist_counts[name] = 0
        artist_counts[name] += 1

    probability_sum = 0
    for row in rows:
        name = row[NAME_COL].lower()
        probability_sum += row[WEIGHT_COL] / artist_counts[name]

    rnd = random.random() * probability_sum
    for row in rows:
        name = row[NAME_COL].lower()
        weight = row[WEIGHT_COL] / artist_counts[name]
        if rnd < weight:
            return row[ID_COL]
        rnd -= weight

    if len(rows):
        logging.warning('Bad RND logic, returning first track.')
        return rows[0][ID_COL]

    return None


def get_prerolls_for_labels(labels):
    """Returns ids of valid prerolls that have one of the specified labels."""
    sql = "SELECT tracks.id FROM tracks INNER JOIN labels ON labels.track_id = tracks.id WHERE tracks.weight > 0 AND tracks.filename IS NOT NULL AND labels.label IN (%s)" % ', '.join(['?'] * len(labels))
    return [row[0] for row in ardj.database.fetch(sql, labels)]


def get_prerolls_for_track(track_id):
    """Returns prerolls applicable to the specified track."""
    by_artist = ardj.database.fetch("SELECT t1.id FROM tracks t1 INNER JOIN tracks t2 ON t2.artist = t1.artist INNER JOIN labels l ON l.track_id = t1.id WHERE l.label = 'preroll' AND t2.id = ? AND t1.weight > 0 AND t1.filename IS NOT NULL", (track_id, ))
    by_label = ardj.database.fetch("SELECT t.id, t.title FROM tracks t WHERE t.weight > 0 AND t.filename IS NOT NULL AND t.id IN (SELECT track_id FROM labels WHERE label IN (SELECT l.label || '-preroll' FROM tracks t1 INNER JOIN labels l ON l.track_id = t1.id WHERE t1.id = ?))", (track_id, ))
    return list(set([row[0] for row in by_artist + by_label]))


def add_preroll(track_id, labels=None):
    """Adds a preroll for the specified track.

    Finds prerolls by labels and artist title, picks one and returns its id,
    queueing the input track_id.  If `labels' is explicitly specified, only
    tracks with those labels will be used as prerolls.

    Tracks that have a preroll-* never have a preroll.
    """
    # Skip if the track is a preroll.
    logging.debug("Looking for prerolls for track %u (labels=%s)" % (track_id, labels))

    row = ardj.database.fetchone("SELECT COUNT(*) FROM labels WHERE track_id = ? AND label LIKE 'preroll-%'", (track_id, ))
    if row and row[0]:
        logging.debug("Track %u is a preroll itself." % track_id)
        return track_id

    if labels:
        prerolls = get_prerolls_for_labels(labels)
    else:
        prerolls = get_prerolls_for_track(track_id)

    logging.debug("Found %u prerolls." % len(prerolls))

    if track_id in prerolls:
        prerolls.remove(track_id)

    if prerolls:
        queue(track_id)
        track_id = prerolls[random.randrange(len(prerolls))]
        logging.debug("Will play track %u (a preroll)." % track_id)

    return track_id


def get_next_track():
    try:
        track_id = get_next_track_id()
        if not track_id:
            logging.warning("Could not find a track to play -- empty database?")
            return None

        track = get_track_by_id(track_id)
        if not track:
            logging.warning("No info on track %s" % track_id)
            return None

        dump_filename = ardj.settings.get("dump_last_track")
        if dump_filename is not None:
            dump = json.dumps(track)
            file(dump_filename, "wb").write(dump.encode("utf-8"))

        return track
    except Exception, e:
        logging.exception("Could not get a track to play: %s" % e)
        return None


def get_next_track_id(update_stats=True):
    """
    Picks a track to play.

    The track is chosen from the active playlists. If nothing could be chosen,
    a random track is picked regardless of the playlist (e.g., the track can be
    in no playlist or in an unexisting one).  If that fails too, None is
    returned.

    Normally returns a dictionary with keys that corresponds to the "tracks"
    table fields, e.g.: filename, artist, title, length, weight, count,
    last_played, playlist.  An additional key is filepath, which contains the
    full path name to the picked track, encoded in UTF-8.

    Before the track is returned, its and the playlist's statistics are
    updated.

    Arguments:
    update_stats -- set to False to not update last_played.
    """
    want_preroll = True
    debug = ardj.settings.get("debug_playlists") == "yes"

    skip_artists = list(set([row[0] for row in ardj.database.fetch('SELECT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(ardj.settings.get('dupes', 5)))]))
    if debug:
        msg = u'Artists to skip: %s' % u', '.join(skip_artists or ['none']) + u'.'
        logging.debug(msg.encode("utf-8"))

    track_id = get_track_id_from_queue()
    if track_id:
        want_preroll = False
        if debug:
            logging.debug('Picked track %u from the queue.' % track_id)

    if not track_id:
        labels = get_urgent()
        if labels:
            track_id = get_random_track_id_from_playlist({'labels': labels}, skip_artists)
            if debug and track_id:
                logging.debug('Picked track %u from the urgent playlist.' % track_id)

    if not track_id:
        for playlist in Playlist.get_active():
            if debug:
                logging.debug('Looking for tracks in playlist "%s"' % playlist.get('name', 'unnamed').encode("utf-8"))
            labels = playlist.get('labels', [playlist.get('name', 'music')])
            track_id = get_random_track_id_from_playlist(playlist, skip_artists)
            if track_id is not None:
                update_program_name(playlist.get("program"))
                s = Sticky()

                msg = 'Picked track %u from playlist "%s" using strategy "%s"' % (track_id, playlist.get('name', 'unnamed').encode("utf-8"), playlist.get("strategy", "default"))
                if s["label"]:
                    msg += " and sticky label \"%s\"" % s["label"]
                logging.debug("%s." % msg)
                break

    if not track_id:
        logging.debug("Falling back to just any random track from the database.")

        rows = ardj.database.fetch("SELECT id, weight, artist, count, last_played FROM tracks WHERE weight > 0")
        track_id = get_random_row(rows)

    if track_id:
        if want_preroll:
            track_id = add_preroll(track_id)

        if update_stats:
            count = ardj.database.fetch('SELECT count FROM tracks WHERE id = ?', (track_id, ))[0][0] or 0
            ardj.database.execute('UPDATE tracks SET count = ?, last_played = ? WHERE id = ?', (count + 1, int(time.time()), track_id, ))

            Playlist.touch_by_track(track_id)

            log(track_id)

        shift_track_weight(track_id)

    return track_id


def update_program_name(name):
    """Updates the current program name.

    Only works if the playlist has a non-empty "program" property. The value is
    written to a text file specified in the program_name_file config file
    property."""
    if not name:
        return

    filename = ardj.settings.get("program_name_file")
    if not filename:
        return

    current = None
    if os.path.exists(filename):
        current = file(filename, "rb").read().decode("utf-8").strip()

    if current != name:
        file(filename, "wb").write(name.encode("utf-8"))

        if ardj.settings.get("program_name_announce"):
            logging.debug("Program name changed from \"%s\" to \"%s\", announcing to the chat room." % (current.encode("utf-8"), name.encode("utf-8")))
            ardj.jabber.chat_say("Program \"%s\" started." % name)
        else:
            logging.debug("Program name changed from \"%s\" to \"%s\"." % (current.encode("utf-8"), name.encode("utf-8")))

        command = ardj.settings.getpath("program_name_handler")
        if os.path.exists(command):
            logging.info("Running %s (%s)" % (command.encode("utf-8"), name.encode("utf-8")))
            subprocess.Popen(command.split(" "), stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def shift_track_weight(track_id):
    logging.debug("Shifting weight for track %u" % track_id)
    weight, real_weight = ardj.database.fetchone("SELECT weight, real_weight FROM tracks WHERE id = ?", (track_id, ))
    if weight < real_weight:
        weight = min(weight + 0.1, real_weight)
    elif weight > real_weight:
        weight = max(weight - 0.1, real_weight)
    ardj.database.execute("UPDATE tracks SET weight = ? WHERE id = ?", (weight, track_id, ))


def log(track_id, listener_count=None, ts=None):
    """Logs that the track was played.

    Only logs tracks with more than zero listeners."""
    if listener_count is None:
        listener_count = ardj.listeners.get_count()
    ardj.database.execute('INSERT INTO playlog (ts, track_id, listeners) VALUES (?, ?, ?)', (int(ts or time.time()), int(track_id), listener_count, ))


def update_real_track_weight(track_id):
    """Returns the real track weight, using the last vote for each user."""
    rows = ardj.database.fetch('SELECT v.email, v.vote * k.weight FROM votes v '
        'INNER JOIN karma k ON k.email = v.email '
        'WHERE v.track_id = ? ORDER BY v.ts', (track_id, ))

    results = {}
    for email, vote in rows:
        results[email] = vote

    real_weight = max(sum(results.values()) * 0.25 + 1, 0.01)
    ardj.database.execute('UPDATE tracks SET real_weight = ? WHERE id = ?', (real_weight, track_id, ))
    return real_weight


def update_real_track_weights():
    """Updates the real_weight column for all tracks.  To be used when the
    votes table was heavily modified or when corruption is possible."""
    update_karma()
    for row in ardj.database.fetch('SELECT id FROM tracks'):
        update_real_track_weight(row[0])


def update_karma():
    """Updates users karma based on their last voting time."""
    ardj.database.execute('DELETE FROM karma')

    now = int(time.time()) / 86400
    for email, ts in ardj.database.fetch('SELECT email, MAX(ts) FROM votes GROUP BY email'):
        diff = now - ts / 86400
        if diff == 0:
            karma = 1
        elif diff > KARMA_TTL:
            karma = 0
        else:
            karma = (KARMA_TTL - float(diff)) / KARMA_TTL
        if karma:
            ardj.database.execute('INSERT INTO karma (email, weight) VALUES (?, ?)', (email, karma, ))
            if '-q' not in sys.argv:
                print '%.04f\t%s (%u)' % (karma, email, diff)


def merge(id1, id2):
    """Merges two tracks."""
    id1, id2 = sorted([id1, id2])

    t1 = get_track_by_id(id1)
    t2 = get_track_by_id(id2)

    for k in ('real_weight', 'last_played', 'weight'):
        t1[k] = max(t1[k] or 0, t2[k] or 0)
    if t2["count"]:
        t1['count'] += t2['count']

    t1['labels'] = list(set(t1['labels'] + t2['labels']))

    ardj.database.execute('UPDATE labels SET track_id = ? WHERE track_id = ?', (id1, id2, ))
    ardj.database.execute('UPDATE votes SET track_id = ? WHERE track_id = ?', (id1, id2, ))
    ardj.database.execute('UPDATE playlog SET track_id = ? WHERE track_id = ?', (id1, id2, ))

    update_track(t1)

    t2['weight'] = 0
    update_track(t2)

    update_real_track_weight(id1)


def update_track_lengths(only_ids=None):
    rows = ardj.database.fetch('SELECT id, filename, length '
        'FROM tracks WHERE weight > 0 AND filename IS NOT NULL')

    updates = []
    for id, filename, length in rows:
        if only_ids is not None and id not in only_ids:
            continue

        filepath = get_real_track_path(filename)
        if not os.path.exists(filepath):
            logging.warning("File %s is missing." % filepath)
            continue

        tags = ardj.tags.get(filepath)
        if "length" not in tags:
            logging.warning("Length of file %s is unknown." % filepath)
            continue

        if tags["length"] != length:
            print '%u, %s: %s => %s' % (id, filename, length, tags['length'])
            updates.append((tags['length'], id))

    for length, id in updates:
        ardj.database.execute('UPDATE tracks SET length = ? WHERE id = ?', (length, id, ))


def bookmark(track_ids, owner, remove=False):
    """Adds a bookmark label to the specified tracks."""
    label = 'bm:' + owner.lower()
    for track_id in track_ids:
        ardj.database.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label, ))
        if not remove:
            ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label, owner, ))


def find_by_artist(artist_name):
    rows = ardj.database.fetch('SELECT id FROM tracks WHERE artist = ? COLLATE unicode', (artist_name, ))
    return [row[0] for row in rows]


def find_by_filename(pattern):
    rows = ardj.database.fetch('SELECT id FROM tracks WHERE filename LIKE ? COLLATE unicode', (pattern, ))
    return [row[0] for row in rows]


def find_by_title(title, artist_name=None):
    """Returns track ids by title."""
    if artist_name is None:
        rows = ardj.database.fetch('SELECT id FROM tracks WHERE title = ? COLLATE unicode', (title, ))
    else:
        rows = ardj.database.fetch('SELECT id FROM tracks WHERE title = ? COLLATE unicode AND artist = ? COLLATE unicode', (title, artist_name, ))
    return [row[0] for row in rows]


def get_missing_tracks(tracklist, limit=100):
    """Removes duplicate and existing tracks."""
    tmp = {}
    fix = ardj.util.lower

    for track in tracklist:
        artist = fix(track['artist'])
        if not artist in tmp:
            tmp[artist] = {}
        if len(tmp[artist]) >= limit:
            continue
        if find_by_title(track['title'], artist):
            continue
        tmp[artist][fix(track['title'])] = track

    result = []
    for artist in sorted(tmp.keys()):
        for title in sorted(tmp[artist].keys()):
            result.append(tmp[artist][title])

    return result


def get_new_tracks(artist_names=None, label='music', weight=1.5):
    if not artist_names:
        artist_names = ardj.database.Open().get_artist_names(label, weight)

    tracklist = ardj.jamendo.find_new_tracks(artist_names)
    tracklist += ardj.podcast.find_new_tracks(artist_names)

    cli = ardj.scrobbler.LastFM().authorize()
    if cli is not None:
        for artist_name in artist_names:
            tracklist += cli.get_tracks_by_artist(artist_name)

    if is_verbose():
        print 'Total tracks: %u.' % len(tracklist)

    return get_missing_tracks(tracklist, limit=ardj.settings.get('fresh_music/tracks_per_artist', 2))


def mark_long():
    """Marks long tracks with the @long tag."""
    tag = "long"
    length = Track2.get_average_length()
    ardj.database.execute("DELETE FROM `labels` WHERE `label` = ?", (tag, ))
    ardj.database.execute("INSERT INTO `labels` (`track_id`, `email`, `label`) SELECT id, \'ardj\', ? FROM tracks WHERE length > ?", (tag, length, ))
    count = ardj.database.fetch('SELECT COUNT(*) FROM labels WHERE label = ?', (tag, ))[0][0]
    ardj.database.commit()
    return length, count


def find_new_tracks(args, label='music', weight=1.5):
    """Finds new tracks by known artists, downloads and adds them."""
    tracks = get_new_tracks(args, label=label, weight=weight)

    if is_verbose():
        print 'New tracks: %u.' % len(tracks)

    added = 0
    artist_names = []
    for track in tracks:
        if is_verbose():
            print "Track:", track
        logging.info((u'[%u/%u] fetching "%s" by %s' % (added + 1, len(tracks), track['title'], track['artist'])).encode("utf-8"))
        try:
            if track['artist'] not in artist_names:
                artist_names.append(track['artist'])
            filename = ardj.util.fetch(str(track['url']), suffix=track.get('suffix'))
            if not is_dry_run():
                add_file(str(filename), add_labels=track.get('tags', ['tagme', 'music']),
                    artist=track["artist"], title=track["title"], dlink=track['url'])
            added += 1
        except KeyboardInterrupt:
            raise
        except Exception, e:
            logging.error((u"Could not download \"%s\" by %s: %s" % (track['title'], track['artist'], e)).encode("utf-8"))

    if added:
        logging.info('Total catch: %u tracks.' % added)
        if not is_dry_run():
            ardj.jabber.chat_say('Downloaded %u new tracks by %s.' % (added, ardj.util.shortlist(sorted(artist_names))))

            db = ardj.database.Open()
            db.mark_recent_music()
            db.mark_orphans()
            mark_long()

    return added


def schedule_download(artist, owner=None):
    """Schedules an artist for downloading from Last.fm or Jamendo."""
    count = ardj.database.fetchone('SELECT COUNT (*) FROM tracks WHERE weight > 0 AND artist = ? COLLATE unicode', (artist, ))
    if count[0]:
        return u'Песни этого исполнителя уже есть.  Новые песни загружаются автоматически в фоновом режиме.'

    ardj.database.execute("INSERT INTO download_queue (artist, owner) VALUES (?, ?)", (artist, owner, ))
    ardj.database.commit()

    return u"Это займёт какое-то время, я сообщу о результате."


def add_label_to_tracks_liked_by(label, jids, sender):
    """Adds the specified to tracks liked by all of the specified jids."""
    if not isinstance(jids, (list, tuple)):
        raise TypeError("jids must be a list or a tuple")

    _sets = [set(ardj.database.fetchcol("SELECT track_id FROM votes WHERE email = ? AND vote > 0", (jid, ))) for jid in jids]
    while len(_sets) > 1:
        _sets[0] &= _sets[1]
        del _sets[1]

    _ids = list(_sets[0])

    ardj.database.execute("DELETE FROM labels WHERE label = ?", (label, ))
    for _id in _ids:
        ardj.database.execute("INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)", (_id, label, sender, ))

    return len(_ids)


def _add_jamendo_meta(track):
    """Updates metadata from Jamendo.  Currently only adds a download link
    (when necessary), because other metadata that Jamendo provides is crappy
    and unreliable."""
    info = ardj.jamendo.get_track_info(track["artist"], track["title"])
    if info is None:
        return

    if info.get("stream") and not track.get("download"):
        track.set_download(info["stream"])


def add_missing_lastfm_tags():
    cli = ardj.scrobbler.LastFM()

    skip_labels = set(ardj.settings.get_scrobbler_skip_labels())

    tracks = ardj.database.Track.find_without_lastfm_tags()
    for track in sorted(tracks, key=lambda t: t["id"], reverse=True):
        labels = track.get_labels()

        if skip_labels and set(labels) & skip_labels:
            info = {"tags": ["notfound", "noartist"]}
            print "  implicit notfound, noartist"
        else:
            _add_jamendo_meta(track)

            try:
                info = cli.get_track_info_ex(track["artist"], track["title"])
            except ardj.scrobbler.TrackNotFound:
                # print "  track not found"
                info = {"tags": ["notfound"], "image": None, "download": None}
                if not cli.is_artist(track["artist"]):
                    info["tags"].append("noartist")
                    # print "  artist not found"
            except ardj.scrobbler.BadAuth, e:
                ardj.log.log_error(str(e), e)
                break
            except ardj.scrobbler.Error, e:
                ardj.log.log_error(str(e), e)
                continue
            except Exception, e:
                ardj.log.log_error(str(e), e)
                continue

        lastfm_tags = info["tags"]

        # Add a dummy tag to avoid scanning this track again.  To rescan,
        # delete this tag and scan again periodically.
        if not lastfm_tags:
            lastfm_tags = ["none"]

        print "%6u. %s -- %s" % (track["id"], track["artist"].encode("utf-8"), track["title"].encode("utf-8"))
        print "        %s" % ", ".join(lastfm_tags)

        for tag in lastfm_tags:
            labels.append("lastfm:" + tag.replace(" ", "_"))

        track.set_labels(labels)
        if info.get("image"):
            track.set_image(info["image"])
        if info.get("download"):
            track.set_download(info["download"])

        logging.debug("Updated track %u with: %s" % (track["id"], info))

        ardj.database.commit()


def do_idle_tasks(set_busy=None):
    """Loads new tracks from external sources."""
    req = ardj.database.fetchone("SELECT artist, owner FROM download_queue LIMIT 1")
    if req is None:
        return False

    artist_name, sender = req

    logging.info((u'Looking for tracks by "%s", requested by %s' % (artist_name, sender)).encode("utf-8"))

    if set_busy is not None:
        set_busy()

    count = find_new_tracks([artist_name])
    if count:
        msg = u"Added %u tracks by %s." % (count, artist_name)
        ardj.jabber.chat_say(msg)
    else:
        msg = u"Could not find anything by %s on Last.fm and Jamendo." % artist_name
    ardj.jabber.chat_say(msg, recipient=sender)

    ardj.database.execute(u"DELETE FROM download_queue WHERE artist = ?", (artist_name, ))
    ardj.database.commit()


class MediaFolderScanner(object):
    """Media folder scanner used for adding new tracks to the database."""

    temp_label = "just_added"

    def run(self):
        """Scans the media folder and adds new tracks.  Tracks that were previously
        deleted aren't added back again."""
        fs = self.find_files()
        db = self.find_tracks()

        ardj.database.Label.delete_by_name(self.temp_label)

        count = 0
        for fn in fs:
            if fn not in db:
                try:
                    t = ardj.database.Track.from_file(fn)
                    logging.info("New track: %s: \"%s\" by %s" % (t["id"], t["title"], t["artist"]))
                    count += 1
                except Exception, e:
                    logging.exception(str(e))

        ardj.database.commit()
        return count

    def find_files(self):
        found_files = []

        root = ardj.settings.get_music_dir()
        for folder, folders, files in os.walk(root):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in (".mp3", ".ogg", ".oga", "flac"):
                    found_files.append(os.path.join(folder, file)[len(root) + 1:])

        return found_files

    def find_tracks(self):
        result = {}
        for track in ardj.database.Track.find_all(deleted=True):
            if track["filename"]:
                result[track["filename"].encode("utf-8")] = track["id"]
        return result


def dedup_by_filename(verbose=False):
    """Finds tracks that link to the same file and merges them, higher ID to lower."""
    cache = {}

    merge_count = 0

    for track in ardj.database.Track.find_all(deleted=False):
        if not track["weight"]:
            continue

        if track["filename"] in cache:
            if verbose:
                print "Duplicate: %u, %s" % (track["id"], track["filename"])
            merge(cache[track["filename"]], track["id"])
            merge_count += 1
        else:
            cache[track["filename"]] = track["id"]

    return merge_count


def count_available():
    """Returns the number of tracks that are not deleted."""
    count = ardj.database.fetch("SELECT COUNT(*) FROM tracks WHERE weight > 0")
    return count[0][0]


def get_track_to_play_next():
    """
    Describes track to play next

    Queries the database, on failure returns a predefined track.
    """

    import database
    import settings

    music_dir = settings.get_music_dir()

    try:
        track = get_next_track()
        if track is not None:
            filepath = os.path.join(music_dir, track["filepath"])
            track.refresh_tags(filepath)
            database.commit()
            track["filepath"] = filepath
            return track
    except Exception, e:
        logging.error("ERROR: %s" % e)

    count = count_available()
    if not count:
        logging.warning("There are NO tracks in the database.  Put some files in %s, then run 'ardj tracks scan'." % music_dir)
    else:
        logging.warning("Could not pick a track to play.  Details can be found in %s." % settings.getpath("log", "syslog"))

    from util import find_sample_music, shared_file
    samples = find_sample_music()
    if samples:
        logging.warning("Playing a pre-packaged file.")
        sample = random.choice(samples)
        return {"filepath": os.path.realpath(sample)}

    else:
        failure = shared_file("audio/stefano_mocini_leaving_you_failure_edit.ogg")
        if failure:
            return {"filepath": os.path.realpath(failure)}
        else:
            logging.warning("Could not find sample music.")


def cmd_scan():
    """Remove tracks with no files, add new ones"""
    import database
    database.Open().purge()
    purge()

    count = MediaFolderScanner().run()
    print "Found %u new files." % count

    database.commit()


def cmd_fix_length():
    """Update track lengths from files (if changed)"""
    from database import commit
    ids = [int(n) for n in args if n.isdigit()]
    update_track_lengths(ids)
    commit()


def cmd_shift_weight():
    """Shift current weights to real weights"""
    from database import commit
    update_real_track_weights()
    commit()


def cmd_next():
    """Print file name to play next."""
    track = get_track_to_play_next()
    if track:
        print track


def cmd_export_csv():
    """Export track info as CSV"""
    from database import Track

    print "id,filename,artist,title,weight,count"
    for track in Track.find_all():
        cells = [track["id"], track["filename"],
            track["artist"] or "Unknown Artist",
            track["title"] or "Untitled",
            track["real_weight"] or "1.0",
            track["count"] or "0"]
        print ",".join([unicode(c).encode("utf-8")
            for c in cells])
