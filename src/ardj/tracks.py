# encoding=utf-8

"""Track management for ardj.

Contains functions that interact with the database in order to modify or query
tracks.
"""

import hashlib
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import traceback

import ardj.database
import ardj.jabber
import ardj.jamendo
import ardj.listeners
import ardj.podcast
import ardj.replaygain
import ardj.scrobbler
import ardj.tags
import ardj.util


KARMA_TTL = 30.0


class Playlist(dict):
    def add_ts(self, stats):
        self['last_played'] = 0
        if self['name'] in stats:
            self['last_played'] = stats[self['name']]
        return self

    def match_track(self, track):
        if type(track) != dict:
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

        if 'delay' in self and self['delay'] * 60 + self['last_played'] >= now_ts:
            return False
        if 'hours' in self and now_hour not in self.get_hours():
            return False
        if 'days' in self and now_day not in self.get_days():
            return False
        return True

    def get_days(self):
        return ardj.util.expand(self['days'])

    def get_hours(self):
        return ardj.util.expand(self['hours'])

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
                logging.debug('Track %u touches playlist "%s".' % (track_id, name))
                rowcount = ardj.database.execute('UPDATE playlists SET last_played = ? WHERE name = ?', (ts, name, ))
                if rowcount == 0:
                    ardj.database.execute('INSERT INTO playlists (name, last_played) VALUES (?, ?)', (name, ts, ))


def get_real_track_path(filename):
    return os.path.join(ardj.settings.get_music_dir(), filename)


def get_track_by_id(track_id):
    """Returns track description as a dictionary.

    If the track does not exist, returns None.  Extended properties,
    such as labels, are also returned.

    Arguments:
    track_id -- identified the track to return.
    cur -- unused.
    """
    rows = ardj.database.fetch("SELECT id, filename, artist, title, length, NULL, weight, count, last_played, real_weight FROM tracks WHERE id = ?", (track_id, ))
    if rows:
        row = rows[0]
        result = {'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'length': row[4], 'weight': row[6], 'count': row[7], 'last_played': row[8], 'real_weight': row[9]}
        result['labels'] = [row[0] for row in ardj.database.fetch('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (track_id, ))]
        if result.get('filename'):
            result['filepath'] = get_real_track_path(result['filename'])
        return result


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
        elif arg.startswith('@'):
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

    for label in search_labels:
        where.append('id IN (SELECT track_id FROM labels WHERE label = ?)')
        params.append(label)

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


def add_labels(track_id, labels, owner=None):
    if labels:
        for label in labels:
            if label.startswith('-'):
                ardj.database.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('-'), ))
            elif ardj.database.fetch('SELECT 1 FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('+'), )):
                pass
            else:
                ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label.lstrip('+'), owner or 'ardj', ))
    return sorted(list(set([row[0] for row in ardj.database.fetch('SELECT label FROM labels WHERE track_id = ?', (track_id, ))])))


def update_track(properties):
    """Updates valid track attributes.

    Loads the track specified in properties['id'], then updates its known
    fields with the rest of the properties dictionary, then saves the
    track.  If there's the "labels" key in properties (must be a list),
    labels are added (old are preserved) to the `labels` table.

    If there's not fields to update, a message is written to the debug log.
    """
    if type(properties) != dict:
        raise Exception('Track properties must be passed as a dictionary.')
    if 'id' not in properties:
        raise Exception('Track properties have no id.')

    sql = []
    params = []
    for k in properties:
        if k in ('filename', 'artist', 'title', 'length', 'weight', 'count', 'last_played', 'owner', 'real_weight'):
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

    # Normalize the vote.
    if vote > 0:
        vote = 1
    elif vote < 0:
        vote = -1

    # Resolve aliases.
    for k, v in ardj.settings.get2("jabber_aliases", "jabber/aliases", {}).items():
        if email in v:
            email = k
            break

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


def gen_filename(suffix):
    """Generates a local file name.

    Returns a tuple (abs_filename, rel_filename).
    """
    musicdir = ardj.settings.get_music_dir()

    while True:
        m = hashlib.md5()
        m.update(str(random.random()))
        name = m.hexdigest() + suffix
        rel_filename = os.path.join(name[0], name[1], name)
        abs_filename = os.path.join(musicdir, rel_filename)
        if not os.path.exists(abs_filename):
            return abs_filename, rel_filename


def add_file(filename, add_labels=None, owner=None, quiet=False):
    """Adds the file to the database.

    Returns track id.
    """
    if not os.path.exists(filename):
        raise Exception('File not found: %s' % filename)

    if not quiet:
        logging.info('Adding from %s' % filename)
    ardj.replaygain.update(filename)

    tags = ardj.tags.get(str(filename)) or {}
    artist = tags.get('artist', 'Unknown Artist')
    title = tags.get('title', 'Untitled')
    duration = tags.get('length', 0)
    labels = tags.get('labels', [])

    if add_labels and not labels:
        labels = add_labels

    abs_filename, rel_filename = gen_filename(os.path.splitext(filename)[1])
    if not ardj.util.copy_file(filename, abs_filename):
        raise Exception('Could not copy %s to %s' % (filename, abs_filename))

    track_id = ardj.database.execute('INSERT INTO tracks (artist, title, filename, length, last_played, owner, weight, real_weight, count) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 0)', (artist, title, rel_filename, duration, 0, owner or 'ardj', ))
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
        if not track.get('filename'):
            return None
        return row[1]


def get_random_track_id_from_playlist(playlist, skip_artists):
    sql = 'SELECT id, weight, artist, count FROM tracks WHERE weight > 0 AND artist IS NOT NULL AND filename IS NOT NULL'
    params = []

    sql, params = add_labels_filter(sql, params, playlist.get('labels', [playlist.get('name', 'music')]))

    repeat_count = playlist.get('repeat')
    if repeat_count:
        sql += ' AND count < ?'
        params.append(int(repeat_count))

    if skip_artists:
        skip_artists = skip_artists[:int(playlist.get('history', '10'))]
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

    if playlist.get('preroll'):
        track_id = add_preroll(track_id, playlist.get('preroll'))

    return track_id


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
        ID_COL, WEIGHT_COL, NAME_COL, COUNT_COL = 0, 1, 2, 3
        rows.sort(key=lambda row: row[COUNT_COL])
        row = random.choice(rows[:5])
        track_id = row[ID_COL]

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
    if ardj.database.fetch("SELECT COUNT(*) FROM labels WHERE track_id = ? AND label LIKE 'preroll-%'", (track_id, ))[0]:
        return track_id

    if labels:
        prerolls = get_prerolls_for_labels(labels)
    else:
        prerolls = get_prerolls_for_track(track_id)

    if track_id in prerolls:
        prerolls.remove(track_id)

    if prerolls:
        queue(track_id)
        track_id = prerolls[random.randrange(len(prerolls))]

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
        logging.error("Could not get a track to play: %s\n%s" % (e, traceback.format_exc(e)))
        return None


def get_next_track_id(debug=False, update_stats=True):
    """Picks a track to play.

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

    skip_artists = list(set([row[0] for row in ardj.database.fetch('SELECT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(ardj.settings.get('dupes', 5)))]))
    if debug:
        logging.debug(u'Artists to skip: %s' % u', '.join(skip_artists or ['none']) + u'.')

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
                logging.debug('Looking for tracks in playlist "%s"' % playlist.get('name', 'unnamed'))
            labels = playlist.get('labels', [playlist.get('name', 'music')])
            track_id = get_random_track_id_from_playlist(playlist, skip_artists)
            if track_id is not None:
                update_program_name(playlist.get("program"))
                logging.debug('Picked track %u from playlist %s' % (track_id, playlist.get('name', 'unnamed')))
                break

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
            logging.debug("Program name changed from \"%s\" to \"%s\", announcing to the chat room." % (current, name))
            ardj.jabber.chat_say("Program \"%s\" started." % name)
        else:
            logging.debug("Program name changed from \"%s\" to \"%s\"." % (current, name))

        command = ardj.settings.getpath("program_name_handler")
        if os.path.exists(command):
            logging.info(u"Running %s (%s)" % (command, name))
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
    if listener_count > 0:
        ardj.database.execute('INSERT INTO playlog (ts, track_id, listeners) VALUES (?, ?, ?)', (int(ts or time.time()), int(track_id), listener_count, ))


def get_average_length():
    """Returns the weighed average track length in seconds."""
    s_prc = s_qty = 0.0
    for prc, qty in ardj.database.fetch('SELECT ROUND(length / 60) AS r, COUNT(*) FROM tracks GROUP BY r'):
        s_prc += prc * qty
        s_qty += qty
    return int(s_prc / s_qty * 60 * 1.5)


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
    t1 = get_track_by_id(id1)
    t2 = get_track_by_id(id2)

    for k in ('real_weight', 'last_played', 'weight'):
        t1[k] = max(t1[k], t2[k])
    t1['count'] = t1['count'] + t2['count']

    t1['labels'] = list(set(t1['labels'] + t2['labels']))

    ardj.database.execute('UPDATE labels SET track_id = ? WHERE track_id = ?', (id1, id2, ))
    ardj.database.execute('UPDATE votes SET track_id = ? WHERE track_id = ?', (id1, id2, ))
    ardj.database.execute('UPDATE playlog SET track_id = ? WHERE track_id = ?', (id1, id2, ))

    update_track(t1)

    t2['weight'] = 0
    update_track(t2)

    update_real_track_weight(id1)


def update_track_lengths():
    rows = ardj.database.fetch('SELECT id, filename, length '
        'FROM tracks WHERE weight > 0 AND filename')

    updates = []
    for id, filename, length in rows:
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


def find_incoming_files(delay=0, verbose=False):
    """Returns a list of incoming file names.  Only files modified more than 60
    seconds ago are reported.  If the database/incoming/path parameter is not
    set, an empty list is returned."""
    result = []

    incoming = ardj.settings.getpath("incoming_path", ardj.settings.getpath('database/incoming/path'))
    if verbose:
        print "Looking for audio files in folder %s" % incoming

    ts_limit = int(time.time()) - delay
    if incoming:
        for dir, dirs, files in os.walk(incoming):
            if not os.access(dir, os.W_OK):
                logging.warning("Folder %s is write protected. Can't delete files, won't add them." % dir)
                continue  # not writable -- can't delete, skip it
            for filename in files:
                realname = os.path.join(dir, filename)
                if os.stat(realname).st_mtime > ts_limit:
                    return []  # still uploading
                if os.path.splitext(filename.lower())[1] in ('.mp3', '.ogg'):
                    result.append(realname)
    return result


def add_incoming_files(filenames):
    """Adds files to the database."""
    success = []
    add_labels = ardj.settings.get("incoming_labels", ardj.settings.get("database/incoming/labels", ["tagme", "music"]))
    for filename in filenames:
        add_file(filename, add_labels)
        os.unlink(filename)
        success.append(os.path.basename(filename))
    ardj.database.commit()
    return success


def bookmark(track_ids, owner, remove=False):
    """Adds a bookmark label to the specified tracks."""
    label = 'bm:' + owner.lower()
    for track_id in track_ids:
        ardj.database.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label, ))
        if not remove:
            ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label, owner, ))


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

    print 'Total tracks: %u.' % len(tracklist)
    return get_missing_tracks(tracklist, limit=ardj.settings.get('fresh_music/tracks_per_artist', 2))


def find_new_tracks(args, label='music', weight=1.5):
    """Finds new tracks by known artists, downloads and adds them."""
    tracks = get_new_tracks(args, label=label, weight=weight)
    print 'New tracks: %u.' % len(tracks)

    added = 0
    artist_names = []
    for track in tracks:
        logging.info(u'[%u/%u] fetching "%s" by %s' % (added + 1, len(tracks), track['title'], track['artist']))
        try:
            if track['artist'] not in artist_names:
                artist_names.append(track['artist'])
            filename = ardj.util.fetch(track['url'], suffix=track.get('suffix'))
            add_file(str(filename), add_labels=track.get('tags', ['tagme', 'music']))
            added += 1
        except KeyboardInterrupt:
            raise
        except:
            pass

    if added:
        logging.info('Total catch: %u tracks.' % added)
        ardj.jabber.chat_say('Downloaded %u new tracks by %s.' % (added, ardj.util.shortlist(sorted(artist_names))))

        db = ardj.database.Open()
        db.mark_recent_music()
        db.mark_orphans()
        db.mark_long()

    return added


def schedule_download(artist, owner=None):
    """Schedules an artist for downloading from Last.fm or Jamendo."""
    count = ardj.database.fetchone('SELECT COUNT (*) FROM tracks WHERE artist = ? COLLATE unicode', (artist, ))
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


def do_idle_tasks(set_busy=None):
    """Loads new tracks from external sources."""
    req = ardj.database.fetchone("SELECT artist, owner FROM download_queue LIMIT 1")
    if req is None:
        return False

    artist_name, sender = req

    logging.info(u'Looking for tracks by "%s", requested by %s' % (artist_name, sender))

    if set_busy is not None:
        set_busy()

    count = find_new_tracks([artist_name])
    if count:
        msg = u"Added %u tracks by %s." % (count, artist_name)
        ardj.chat_say(msg)
    else:
        msg = u"Could not find anything by %s on Last.fm and Jamendo." % artist_name
    ardj.jabber.chat_say(msg, recipient=sender)

    ardj.database.execute(u"DELETE FROM download_queue WHERE artist = ?", (artist_name, ))
    ardj.database.commit()
