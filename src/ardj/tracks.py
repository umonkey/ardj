# encoding=utf-8

"""Track management for ardj.

Contains functions that interact with the database in order to modify or query
tracks.
"""

import hashlib
import json
import os
import random
import re
import sys
import time

import ardj.database
import ardj.jabber
import ardj.jamendo
import ardj.listeners
import ardj.log
import ardj.podcast
import ardj.replaygain
import ardj.scrobbler
import ardj.tags
import ardj.util

from ardj.playlist import Playlist

KARMA_TTL = 30.0


class Track(dict):
    """Wraps a track."""
    @classmethod
    def get_by_id(cls, track_id):
        return cls(ardj.database.Open().get_track_by_id(track_id))

    @classmethod
    def get_next(cls, ts=None, update_stats=True):
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
        if ts is None:
            ts = int(time.time())

        db = ardj.database.Open()

        track = cls.get_from_queue()
        if track is None:
            track = cls.get_from_playlists(ts)

        if track and update_stats:
            track.touch(ts)
            for playlist in Playlist.get_by_labels(track["labels"]):
                playlist.touch(ts)

        return track

    @classmethod
    def get_from_playlists(cls, timestamp):
        """Returns a track from an active playlist."""
        for playlist in Playlist.get_active(timestamp):
            tracks = playlist.get_tracks(timestamp)
            if tracks:
                track = cls(cls.pick_random(tracks))
                if track is not None:
                    track = track.add_preroll(playlist)
                return track

    @classmethod
    def get_from_queue(cls):
        """Returns a track from the top of the queue, removes it from there."""
        db = ardj.database.Open()
        queue = db.get_queue()
        if queue:
            track = cls.get_by_id(queue[0]["track_id"])
            db.remove_from_queue(queue[0]["id"])
            return track

    @classmethod
    def pick_random(cls, tracks):
        """Returns a random row list item, uses weights."""
        if not tracks:
            return None

        if len(tracks) == 1:
            return tracks[0]

        set_final_weights(tracks)
        total = sum([t["final_weight"] for t in tracks])
        limit = random.random() * total

        for track in tracks:
            if limit < track["final_weight"]:
                return track
            limit -= track["final_weight"]

        return tracks[0]  # some weird fallback

    @classmethod
    def get_unique(cls, *chain):
        """Returns unique tracks from all lists."""
        result = {}
        for tracks in chain:
            for track in tracks:
                result[track["id"]] = track
        return result.values()

    @classmethod
    def find(cls, **kwargs):
        return ardj.database.Open().get_tracks(**kwargs)

    @classmethod
    def get_track_to_play(cls):
        """Returns information about the track to play.
        
        The information is requested from an external ardj process, because
        otherwise you would have to restart ices every time the track selection
        algorithm is changed."""
        data = ardj.util.run(["ardj", "show-next-track"], quiet=True, grab_output=True)
        return json.loads(data)

    @classmethod
    def fix_lengths(cls):
        """Updates lengths of all tracks."""
        for track in cls.find(has_filename=True):
            track = cls(track)
            if not os.path.exists(track["filepath"]):
                print "Track %u does not exist on disk." % track["id"]
                continue
            tags = track.get_tags()
            if "length" in tags and tags["length"] != track["length"]:
                track["length"] = tags["length"]
                track.put()

    def update_real_weight(self):
        results = {}
        for vote in ardj.database.Open().get_track_votes(self["id"]):
            results[vote["email"]] = vote["vote"]
        self["real_weight"] = max(sum(results.values()) * 0.25 + 1, 0.01)
        self.put()

    @classmethod
    def update_real_weights(cls):
        """Updates the real_weight column for all tracks.  To be used when the
        votes table was heavily modified or when corruption is possible."""
        update_karma()
        for track in cls.find():
            track = cls(track)
            track.update_real_weight()

    @classmethod
    def get_average_length(cls):
        """Returns average track length in minutes."""
        stats = {}
        for track in cls.find():
            length = round(track["length"])
            if length not in stats:
                stats[length] = 0
            stats[length] += 1

        s_prc = s_qty = 0.0
        for prc, qty in stats.items():
            s_prc += prc * qty
            s_qty += qty

        return int(s_prc / s_qty * 60 * 1.5)

    def add_preroll(self, playlist):
        db = ardj.database.Open()

        labels = self["labels"]
        if "preroll" in playlist:
            labels.extend(playlist["preroll"])

        tracks1 = self.find(labels=labels)
        tracks2 = self.find(labels=["preroll"], artist=self["artist"])

        tracks = self.get_unique(tracks1, tracks2)
        preroll = self.pick_random(tracks)

        if preroll is not None:
            self.add_to_queue()
            return Track(preroll)

        return self

    def add_to_queue(self):
        ardj.database.Open().add_to_queue(self["id"])

    def get_tags(self):
        """Returns track tags."""
        return ardj.tags.get(self["filepath"])

    def touch(self, ts):
        self.update_weight()
        self["count"] += 1
        self["last_played"] = ts
        self.put()
        for playlist in Playlist.get_by_labels(self["labels"]):
            playlist.touch(ts)

    def update_weight(self):
        if self["weight"] < self["real_weight"]:
            delta = max(self["real_weight"] - self["weight"], 0.1)
        else:
            delta = min(self["weight"] - self["real_weight"], -0.1)
        self["weight"] += delta

    def put(self):
        ardj.database.Open().update_track(self)

    def __getitem__(self, k):
        if k == "labels" and "labels" not in self:
            self["labels"] = ardj.database.Open().get_track_labels(self["id"])
        if k == "filepath":
            return os.path.join(ardj.settings.get_music_dir(), self["filename"])
        return self.get(k)

    def merge_into(self, other):
        if self["id"] == other["id"]:
            return
        for k in ("real_weight", "last_played", "weight"):
            other[k] = max(self[k], other[k])
        other["count"] += self["count"]
        other["labels"] = list(set(self["labels"] + other["labels"]))
        other.put()

        self["weight"] = 0
        self.put()

        ardj.database.Open().merge_tracks(self["id"], other["id"])


def get_last_track_id(cur=None):
    """Returns id of the last played track.

    If the database is empty, returns None, otherwise an integer.

    Keyword arguments:
    cur -- database cursor, created if None.
    """
    cur = cur or ardj.database.cursor()
    row = cur.execute('SELECT id FROM tracks ORDER BY last_played DESC LIMIT 1').fetchone()
    return row and row[0] or None


def get_last_track(cur=None):
    """Returns the full description of the last played track.

    Calls get_track_by_id(get_last_track_id()).
    """
    return Track.get_by_id(get_last_track_id(cur))


def identify(track_id, cur=None, unknown='an unknown track'):
    track = Track.get_by_id(track_id)
    if not track:
        return unknown
    return u'«%s» by %s' % (track.get('title', 'untitled'), track.get('artist', 'unknown artist'))

def queue(track_id, owner=None, cur=None):
    """Adds the track to queue."""
    cur = cur or ardj.database.cursor()
    return cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track_id, (owner or 'ardj').lower(), )).lastrowid


def get_queue(cur=None):
    cur = cur or ardj.database.cursor()
    return [Track.get_by_id(row[0]) for row in cur.execute('SELECT track_id FROM queue ORDER BY id').fetchall()]


def find_ids(pattern, sender=None, cur=None, limit=None):
    cur = cur or ardj.database.cursor()

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
        return [ int(x) for x in search_ids ]

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
    rows = cur.execute(sql, params).fetchall()
    return [row[0] for row in rows]


def add_labels(track_id, labels, owner=None, cur=None):
    cur = cur or ardj.database.cursor()
    if labels:
        for label in labels:
            if label.startswith('-'):
                cur.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('-'), ))
            elif cur.execute('SELECT 1 FROM labels WHERE track_id = ? AND label = ?', (track_id, label.lstrip('+'), )).fetchall():
                pass
            else:
                cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label.lstrip('+'), owner or 'ardj', ))
    return sorted(list(set([row[0] for row in cur.execute('SELECT label FROM labels WHERE track_id = ?', (track_id, )).fetchall()])))


def update_track(properties, cur=None):
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
    cur = cur or ardj.database.cursor()

    sql = []
    params = []
    for k in properties:
        if k in ('filename', 'artist', 'title', 'length', 'weight', 'count', 'last_played', 'owner', 'real_weight'):
            sql.append(k + ' = ?')
            params.append(properties[k])

    if not sql:
        ardj.log.debug('No fields to update.')
    else:
        params.append(properties['id'])
        sql = 'UPDATE tracks SET ' + ', '.join(sql) + ' WHERE id = ?'
        ardj.database.Open().debug(sql, params)
        cur.execute(sql, tuple(params))

    if properties.get('labels'):
        add_labels(properties['id'], properties['labels'], owner=properties.get('owner'), cur=cur)


def purge(cur=None):
    """Deletes tracks with zero weight.

    Removes files, track entries are left in the database to prevent reloading
    by podcaster etc.
    """
    cur = cur or ardj.database.cursor()
    music_dir = ardj.settings.get_music_dir()

    # mark tracks that no longer have files
    for track_id, filename in cur.execute('SELECT id, filename FROM tracks WHERE weight > 0 AND filename IS NOT NULL').fetchall():
        abs_filename = os.path.join(music_dir, filename)
        if not os.path.exists(abs_filename):
            ardj.log.warning('Track %u vanished (%s), deleting.' % (track_id, filename))
            cur.execute('UPDATE tracks SET weight = 0 WHERE id = ?', (track_id, ))

    for track_id, filename in cur.execute('SELECT id, filename FROM tracks WHERE weight = 0 AND filename IS NOT NULL').fetchall():
        abs_filename = os.path.join(music_dir, filename)
        if os.path.exists(abs_filename):
            os.unlink(abs_filename)
            ardj.log.info('Deleted track %u (%s) from file system.' % (track_id, filename))

    cur.execute('UPDATE tracks SET filename = NULL WHERE weight = 0')
    ardj.database.Open().purge(cur)


def get_urgent(cur=None):
    """Returns current playlist preferences."""
    cur = cur or ardj.database.cursor()
    data = cur.execute('SELECT labels FROM urgent_playlists WHERE expires > ? ORDER BY expires', (int(time.time()), )).fetchall()
    if data:
        return re.split('[,\s]+', data[0][0])
    return None


def set_urgent(args, cur=None):
    """Sets the music filter.

    Sets music filter to be used for picking random tracks.  If set, only
    matching tracks will be played, regardless of playlists.yaml.  Labels
    must be specified as a string, using spaces or commas as separators.
    Use "all" to reset.
    """
    cur = cur or ardj.database.cursor()
    cur.execute('DELETE FROM urgent_playlists')
    if args != 'all':
        expires = time.time() + 3600
        cur.execute('INSERT INTO urgent_playlists (labels, expires) VALUES (?, ?)', (args, int(expires), ))


def add_vote(track_id, email, vote, cur=None, update_karma=False):
    """Adds a vote for/against a track.

    The process is: 1) add a record to the votes table, 2) update email's
    record in the karma table, 3) update weight for all tracks email voted
    for/against.

    Votes other than +1 and -1 are skipped.

    Returns track's current weight.
    """
    cur = cur or ardj.database.cursor()

    email = email.lower()

    # Normalize the vote.
    if vote > 0: vote = 1
    elif vote < 0: vote = -1

    # Resolve aliases.
    for k, v in ardj.settings.get('jabber/aliases', {}).items():
        if email in v:
            email = k
            break

    row = cur.execute("SELECT last_played, weight FROM tracks WHERE id = ?", (track_id, )).fetchone()
    if row is None:
        return None

    last_played, current_weight = row
    if not last_played:
        raise Exception('This track was never played.')
    elif current_weight <= 0:
        raise Exception("Can't vote for deleted tracks.")

    vote_count = cur.execute("SELECT COUNT(*) FROM votes WHERE track_id = ? "
        "AND email = ? AND vote = ? AND ts >= ?", (track_id, email, vote,
        last_played, )).fetchone()[0]

    cur.execute('INSERT INTO votes (track_id, email, vote, ts) '
        'VALUES (?, ?, ?, ?)', (track_id, email, vote, int(time.time()), ))

    # Update current track weight.
    if not vote_count:
        current_weight = max(current_weight + vote * 0.25, 0.01)
        cur.execute('UPDATE tracks SET weight = ? WHERE id = ?', (current_weight, track_id, ))

        Track.get_by_id(track_id).update_real_weight()

    real_weight = cur.execute('SELECT weight FROM tracks WHERE id = ?',
        (track_id, )).fetchone()[0]
    return real_weight


def get_vote(track_id, email, cur=None):
    return get_track_votes(track_id, cur=cur).get(email.lower(), 0)


def get_track_votes(track_id, cur=None):
    results = {}
    cur = cur or ardj.database.cursor()
    for email, vote in cur.execute("SELECT email, vote FROM votes WHERE track_id = ? ORDER BY id", (track_id, )).fetchall():
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
        ardj.log.info('Adding from %s' % filename)
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

    cur = ardj.database.cursor()
    track_id = cur.execute('INSERT INTO tracks (artist, title, filename, length, last_played, owner, weight, real_weight, count) VALUES (?, ?, ?, ?, ?, ?, 1, 1, 0)', (artist, title, rel_filename, duration, 0, owner or 'ardj', )).lastrowid
    for label in labels:
        cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)', (track_id, label, (owner or 'ardj').lower(), ))
    ardj.database.commit()
    return track_id


def set_final_weights(tracks):
    """Sets the final_weight property to weight / artist_track_count."""
    result = {}
    for track in tracks:
        name = track["artist"].lower()
        if name not in result:
            result[name] = 0
        result[name] += 1

    for idx, track in enumerate(tracks):
        artist = track["artist"].lower()
        tracks[idx]["final_weight"] = track["weight"] / result[artist]



def log(track_id, listener_count=None, ts=None, cur=None):
    """Logs that the track was played.

    Only logs tracks with more than zero listeners."""
    if listener_count is None:
        listener_count = ardj.listeners.get_count()
    if listener_count > 0:
        cur = cur or ardj.database.cursor()
        cur.execute('INSERT INTO playlog (ts, track_id, listeners) VALUES (?, ?, ?)', (int(ts or time.time()), int(track_id), listener_count, ))


def update_karma(cur=None):
    """Updates users karma based on their last voting time."""
    cur = cur or ardj.database.cursor()

    cur.execute('DELETE FROM karma')

    now = int(time.time()) / 86400
    for email, ts in cur.execute('SELECT email, MAX(ts) FROM votes GROUP BY email').fetchall():
        diff = now - ts / 86400
        if diff == 0:
            karma = 1
        elif diff > KARMA_TTL:
            karma = 0
        else:
            karma = (KARMA_TTL - float(diff)) / KARMA_TTL
        if karma:
            cur.execute('INSERT INTO karma (email, weight) VALUES (?, ?)', (email, karma, ))
            if '-q' not in sys.argv:
                print '%.04f\t%s (%u)' % (karma, email, diff)


def find_incoming_files():
    """Returns a list of incoming file names.  Only files modified more than 60
    seconds ago are reported.  If the database/incoming/path parameter is not
    set, an empty list is returned."""
    result = []
    incoming = ardj.settings.getpath('database/incoming/path')
    ts_limit = int(time.time()) - 120
    if incoming:
        for dir, dirs, files in os.walk(incoming):
            for filename in files:
                realname = os.path.join(dir, filename)
                if os.stat(realname).st_mtime > ts_limit:
                    return [] # still uploading
                if os.path.splitext(filename.lower())[1] in ('.mp3', '.ogg'):
                    result.append(realname)
    return result


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
        if Track.find(title=track["title"], artist=artist, min_weight=-1):
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
        ardj.log.info(u'[%u/%u] fetching "%s" by %s' % (added+1, len(tracks), track['title'], track['artist']))
        try:
            if track['artist'] not in artist_names:
                artist_names.append(track['artist'])
            filename = ardj.util.fetch(track['url'], suffix=track.get('suffix'))
            add_file(str(filename), add_labels=track.get('tags', [ 'tagme', 'music' ]))
            added += 1
        except KeyboardInterrupt: raise
        except: pass

    if added:
        ardj.log.info('Total catch: %u tracks.' % added)
        ardj.jabber.chat_say('Downloaded %u new tracks by %s.' % (added, ardj.util.shortlist(sorted(artist_names))))

        db = ardj.database.Open()
        db.mark_recent_music()
        db.mark_orphans()
        db.mark_long()

    return added


def schedule_download(artist, owner=None):
    """Schedules an artist for downloading from Last.fm or Jamendo."""
    cur = ardj.database.cursor()

    count = cur.execute('SELECT COUNT (*) FROM tracks WHERE artist = ? COLLATE unicode', (artist, )).fetchone()
    if count[0]:
        return u'Песни этого исполнителя уже есть.  Новые песни загружаются автоматически в фоновом режиме.'

    cur.execute('INSERT INTO download_queue (artist, owner) VALUES (?, ?)', (artist, owner, ))
    return u'Это займёт какое-то время, я сообщу о результате.'


def do_idle_tasks(set_busy):
    """Loads new tracks from external sources."""
    cur = ardj.database.cursor()
    row = cur.execute('SELECT artist, owner FROM download_queue LIMIT 1').fetchone()
    if not row:
        return

    ardj.log.info(u'Looking for tracks by "%s", requested by %s' % row)

    set_busy()
    cur.execute('DELETE FROM download_queue WHERE artist = ?', (row[0], ))

    count = find_new_tracks([ row[0] ])
    if count:
        msg = u'Added %u tracks by %s.' % (count, row[0])
    else:
        msg = u'Could not find anything by %s on Last.fm and Jamendo.' % row[0]
    ardj.jabber.chat_say(msg, recipient=row[1], cur=cur)
    ardj.database.commit()


def cli_update_real_weights(args):
    Track.update_real_weights()


def cli_next_track(args):
    """Prints JSON description of the track to play, saves it to ~/last-track.json."""
    track = Track.get_next(update_stats='-n' not in args)
    if track is not None:
        output = json.dumps(track)

        try:
            f = open(ardj.settings.getpath('last_track_json', '~/last-track.json'), 'wb')
            f.write(output)
            f.close()
        except Exception, e:
            ardj.log.error('Could not write last-track.json: %s' % e)

        ardj.log.debug('next-json returns: %s' % output)
        print output


def cli_fix_lengths(args):
    Track.fix_lengths()
