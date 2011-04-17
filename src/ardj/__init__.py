# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:

import hashlib
import os
import random
import re
import shutil
import time

import ardj.database
import ardj.log
import ardj.scrobbler
import ardj.tags
import ardj.util

ardj_instance = None

class old_ardj:
    def __init__(self):
        self.database = ardj.database.Open()
        self.scrobbler = scrobbler.Open()

    def __del__(self):
        self.close()

    def get_next_track(self, scrobble=True):
        """
        Returns information about the next track. The track is chosen from the
        active playlists. If nothing could be chosen, a random track is picked
        regardless of the playlist (e.g., the track can be in no playlist or
        in an unexisting one).  If that fails too, None is returned.

        Normally returns a dictionary with keys that corresponds to the "tracks"
        table fields, e.g.: filename, artist, title, length, artist_weight, weight,
        count, last_played, playlist.  An additional key is filepath, which
        contains the full path name to the picked track, encoded in UTF-8.

        Before the track is returned, its and the playlist's statistics are updated.
        """
        cur = self.database.cursor()
        # Last played artist names.
        skip = self.get_last_artists(cur=cur)

        track = self.__get_queued_track(cur)
        if track is None:
            track = self.__get_urgent_track(skip, cur)
            if track is None:
                track = self.__get_track_from_playlists(skip, cur)
            if track is None:
                track = self.get_random_track(cur=cur)
                if track is not None:
                    ardj.log.info(u'Picked track %u (last resort).' % track['id'])
            track = self._get_preroll(track, cur)
        if track is not None:
            track = self.__fix_track_file_name(track, cur)
            track['count'] += 1
            track['last_played'] = int(time.time())
            track = self.check_track_conditions(track)
            if scrobble and self.scrobbler:
                self.scrobbler.submit(track)
            track['labels'] = [] # prevent updating of labels
            self.database.update_track(track, cur)
            track['filepath'] = os.path.join(ardj.settings.get_music_dir(), track['filename']).encode('utf-8')
            self.database.commit() # без этого параллельные обращения будут висеть
        return track

    def _get_preroll(self, track, cur):
        """
        Finds a preroll for the current track.

        If a preroll is found, it is played instead of the track, which is
        added to the top of queue (to be played next).

        Prerolls are picked in two steps.  First, tracks by the same artist
        that have the "preroll" label are selected.  If nothing was found,
        tracks with the "preroll" label AND one of the current track's labels
        with the "-preroll" suffixes is selected.  For example, if a track with
        labels "voicemail" and "funny" was passed in, prerolls must have the
        "preroll" label and any of "voicemail-preroll" and "funny-preroll".
        """
        if track is None:
            return track

        preroll = self._get_preroll_for_track(track, cur)
        if preroll is not None:
            ardj.log.debug('Playing preroll %s for track %s.' % (preroll['id'], track['id']))
            self._push_to_queue(track, cur)
            track = preroll

        return track

    def _get_preroll_for_track(self, track, cur):
        preroll = self._get_random_track_sql('SELECT id FROM tracks WHERE artist = ? AND id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY RANDOM() LIMIT 1', (track['artist'], 'preroll', ), cur=cur)
        if preroll is None and 'labels' in track and track['labels']:
            label = track['labels'][0] + '-preroll'
            preroll = self._get_random_track_sql('SELECT id FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY RANDOM() LIMIT 1', (label, ), cur=cur)
            if preroll:
                ardj.log.debug('Found a preroll: %s.' % preroll['id'])
        return preroll

    def _push_to_queue(self, track, cur):
        """
        Adds a track to the top of the queue.
        """
        cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track['id'], 'preroll', ))

    def _get_random_track_sql(self, sql, params=None, cur=None):
        """
        Returns a random track from those returned by the SQL statement.

        The SQL statement must return a rowset with track id as the first
        column.  Other columns are ignored and should not be used.

        FIXME: currently returns the first row, add RNG!
        """
        cur = cur or self.database.cursor()
        rows = cur.execute(sql, params).fetchall()
        if not rows:
            return None
        return self.get_track_by_id(rows[0][0], cur)

    def __get_queued_track(self, cur):
        """
        Returns a track from the top of the queue or None.
        """
        row = cur.execute('SELECT id, track_id FROM queue ORDER BY id LIMIT 1').fetchone()
        if row is not None:
            track = self.get_track_by_id(row[1])
            if track is not None:
                ardj.log.info(u'Picked track %s from the top of the queue.' % track['id'])
            else:
                ardj.log.info(u'Picked a non-existing track from the queue.')
            cur.execute('DELETE FROM queue WHERE id = ?', (row[0], ))
            return track

    def __get_urgent_track(self, skip, cur):
        """
        Returns a track from the immediate (urgent) playlist.
        """
        labels = self.database.get_urgent()
        if labels:
            track = self.get_random_track({'labels':labels}, skip_artists=skip, cur=cur)
            if track:
                ardj.log.info(u'Picked track %u from the urgent playlist.' % track['id'])
                return track

    def __get_track_from_playlists(self, skip, cur):
        """
        Returns a track from and active playlist.
        """
        for playlist in self.get_active_playlists():
            track = self.get_random_track(playlist, repeat='repeat' in playlist and playlist['repeat'] or None, skip_artists=skip, cur=cur)
            if track is not None:
                ardj.log.info(u'Picked track %u from playlist %s ("%s" by %s).' % (track['id'], playlist['name'], track['title'], track['artist']))
                cur.execute('UPDATE playlists SET last_played = ? WHERE name = ?', (int(time.time()), playlist['name']))
                return track

    def __add_labels_filter(self, sql, params, labels):
        if type(labels) != list:
            raise Exception('Labels must be a list.')
        normal = [l for l in labels if not l.startswith('+') and not l.startswith('-')]
        if normal:
            sql += ' AND id IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(normal))
            for label in normal:
                params.append(label)
        forbidden = [l[1:] for l in labels if l.startswith('-')]
        if forbidden:
            sql += ' AND id NOT IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(forbidden))
            for label in forbidden:
                params.append(label)
        required = [l[1:] for l in labels if l.startswith('+')]
        if required:
            for label in required:
                sql += ' AND id IN (SELECT track_id FROM labels WHERE label = ?)'
                params.append(label)
        return sql, params

    def __fix_track_file_name(self, track, cur):
        """
        Makes sure the file name is MD5 based.
        """
        if not re.match('[0-9a-f]/[0-9a-f]/[0-9a-f]{32}', os.path.splitext(track['filename'])[0]):
            current_path = os.path.join(ardj.settings.get_music_dir(), track['filename']).encode('utf-8')
            if not os.path.exists(current_path):
                return track
            new_name = self.__get_local_file_name(current_path)
            new_path = os.path.join(ardj.settings.get_music_dir(), new_name)
            new_dir = os.path.dirname(new_path)
            if not os.path.exists(new_dir):
                ardj.log.info(u'Creating folder ' + new_dir)
                os.makedirs(new_dir)
            try:
                shutil.move(current_path, new_path)
                ardj.log.info(u'Moved %s to %s' % (track['filename'], new_name))
                track['filename'] = new_name
                # This can be done later, but can be not, so let's do it to avoid desync.
                cur.execute('UPDATE tracks SET filename = ? WHERE id = ?', (new_name, track['id'], ))
            except:
                ardj.log.info(u'Could move %s to %s' % (track['filename'], new_name))
        return track

    def queue_track(self, id, cur=None):
        """
        Adds a track to the end of the queue.
        """
        return (cur or self.database.cursor()).execute('INSERT INTO queue (track_id) VALUES (?)', (id, )).lastrowid

    def check_track_conditions(self, track):
        """
        Updates track information according to various conditions. Currently
        can only move it to another playlist when play count reaches the limit
        for the current playlist; the target playlist must be specified in
        current playlist's "on_repeat_move_to" property.
        """
        playlist = None # self.get_playlist_by_name(track['playlist']) # FIXME
        if playlist:
            if 'repeat' in playlist and playlist['repeat'] == track['count']:
                if 'on_repeat_move_to' in playlist:
                    track['playlist'] = playlist['on_repeat_move_to']
        return track

    def get_playlist_by_name(self, name):
        for playlist in self.get_playlists():
            if name == playlist['name']:
                return playlist
        return None

    def get_last_artists(self, cur=None):
        """
        Returns the names of last played artists.
        """
        cur = cur or self.database.cursor()
        return list(set([row[0] for row in cur.execute('SELECT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(ardj.settings.get('dupes', 5))).fetchall()]))

    def get_last_track(self):
        """
        Returns a dictionary that describes the last played track.
        """
        cur = self.database.cursor()
        row = cur.execute('SELECT id, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks ORDER BY last_played DESC LIMIT 1').fetchone()
        if row is not None:
            result = { 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'length': row[4], 'artist_weight': row[5], 'weight': row[6], 'count': row[7], 'last_played': row[8] }
            result['labels'] = [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (result['id'], )).fetchall()]
            return result

    def get_track_by_id(self, id, cur=None):
        """
        Returns a dictionary that describes the specified track.
        """
        cur = cur or self.database.cursor()
        row = cur.execute('SELECT id, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks WHERE id = ?', (id, )).fetchone()
        if row is not None:
            result = { 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'length': row[4], 'artist_weight': row[5], 'weight': row[6], 'count': row[7], 'last_played': row[8] }
            result['labels'] = [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (id, )).fetchall()]
            return result

    def get_random_track(self, playlist=None, repeat=None, skip_artists=None, cur=None, labels=None):
        """
        Returns a random track from the specified playlist.  Playlist is a
        dictionary which corresponds to a part of playlists.yaml.  If it has
        labels, they are used, otherwise playlist name is used as the label.
        """
        cur = cur or self.database.cursor()
        if playlist:
            labels = 'labels' in playlist and playlist['labels'] or [playlist['name']]
        else:
            labels = None
        weight = playlist and 'weight' in playlist and playlist['weight'] or None
        delay = playlist and 'track_delay' in playlist and playlist['track_delay'] or None
        id = self.get_random_track_id(labels, repeat, skip_artists, cur, weight, delay)
        if id is not None:
            return self.get_track_by_id(id, cur)

    def get_random_track_id(self, labels=None, repeat=None, skip_artists=None, cur=None, weight=None, delay=None):
        """
        Returns a random track's id.
        """
        cur = cur or self.database.cursor()
        sql = 'SELECT id, weight, artist FROM tracks WHERE weight > 0 AND artist is not NULL'
        params = []
        # filter by labels
        if labels:
            sql, params = self.__add_labels_filter(sql, params, labels)
        # filter by repeat count
        if repeat is not None:
            sql += ' AND count < ?'
            params.append(repeat)
        # filter by recent artists
        if skip_artists is not None:
            tsql = []
            for name in skip_artists:
                tsql.append('?')
                params.append(name)
            sql += ' AND artist NOT IN (' + ', '.join(tsql) + ')'
        # filter by weight
        if weight is not None:
            if weight.endswith('+'):
                sql += ' AND weight >= ?'
                params.append(float(weight[:-1]))
            elif weight.endswith('-'):
                sql += ' AND weight <= ?'
                params.append(float(weight[:-1]))
        # delay some tracks
        if delay is not None:
            ts_limit = int(time.time()) - int(delay) * 60;
            sql += ' AND (last_played IS NULL OR last_played <= ?)'
            params.append(ts_limit)
        ardj.log.debug('SQL: %s; PARAMS: %s' % (sql, params))
        self.database.debug(sql, params)
        return self.get_random_row(cur.execute(sql, tuple(params)).fetchall())

    def get_random_row(self, rows):
        """Picks a random track from a set."""
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
            ardj.log.warning(u'Bad RND logic, returning first track.')
            return rows[0][ID_COL]

        return None

    def get_playlists(self):
        "Returns information about all known playlists."
        stats = dict(self.database.cursor().execute('SELECT name, last_played FROM playlists WHERE name IS NOT NULL AND last_played IS NOT NULL').fetchall())
        def expand(lst):
            result = []
            for item in lst:
                if '-' in str(item):
                    bounds = item.split('-')
                    result += range(int(bounds[0]), int(bounds[1]) + 1)
                else:
                    result.append(item)
            return result
        def add_ts(p):
            p['last_played'] = 0
            if p['name'] in stats:
                p['last_played'] = stats[p['name']]
            if 'days' in p:
                p['days'] = expand(p['days'])
            if 'hours' in p:
                p['hours'] = expand(p['hours'])
            return p
        return [add_ts(p) for p in ardj.settings.get_playlists()]

    def get_active_playlists(self, timestamp=None, explain=False):
        "Returns playlists active at the specified time."
        now = time.localtime(timestamp)

        now_ts = time.mktime(now)
        now_day = int(time.strftime('%w', now))
        now_hour = int(time.strftime('%H', now))

        def is_active(p):
            if 'delay' in p and p['delay'] * 60 + p['last_played'] >= now_ts:
                if explain:
                    print '%s: delayed' % p['name']
                return False
            if 'hours' in p and now_hour not in p['hours']:
                if explain:
                    print '%s: wrong hour (%s not in %s)' % (p['name'], now_hour, p['hours'])
                return False
            if 'days' in p and now_day not in p['days']:
                if explain:
                    print '%s: wrong day (%s not in %s)' % (p['name'], now_day, p['days'])
                return False
            return True

        return [p for p in self.get_playlists() if is_active(p)]

    def close(self):
        """
        Flushes any transactions, closes the database.
        """
        self.database.commit()

    def add_file(self, source_filename, properties=None, queue=False):
        """
        Adds a file to the database or updates it.  Properties, if specified,
        must be a dictionary with keys: owner (email), labels (list), artist,
        title.

        The file is copied to an internal location, the original file can be
        removed afterwards.
        """
        if not os.path.exists(source_filename):
            ardj.log.warning('File %s not found, not adding.' % source_filename)
            return None
        if not os.path.splitext(source_filename.lower())[1] in ('.mp3', '.ogg'):
            ardj.log.warning('File %s has wrong extension, skipping.' % source_filename)
            return None
        filename = self.__get_local_file_name(source_filename)
        filepath = os.path.join(ardj.settings.get_music_dir(), filename)

        if not os.path.exists(filepath):
            ardj.log.info('Copying a file from %s to %s' % (source_filename, filepath))
            dirname = os.path.dirname(filepath)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            shutil.copyfile(source_filename, filepath)

        cur = self.database.cursor()
        properties = self.__get_track_properties(filepath, properties)
        properties['filename'] = filename
        properties['id'] = self.__get_track_id(filename, cur)
        self.database.update_track(properties, cur=cur)
        self.update_artist_weight(properties['artist'], cur)
        if queue:
            owner = 'owner' in properties and properties['owner'] or 'nobody@nowhere.com'
            cur.execute('INSERT INTO queue (track_id, owner) SELECT id, ? FROM tracks WHERE id NOT IN (SELECT track_id FROM queue) AND id = ?', (owner, properties['id'], ))
        return properties['id']

    def update_artist_weight(self, artist, cur=None):
        cur = cur or self.database.cursor()
        row = cur.execute('SELECT COUNT(*) FROM tracks WHERE weight > 0 AND artist = ?', (artist, )).fetchone()
        if row:
            count = float(row[0])
            if count:
                cur.execute('UPDATE tracks SET artist_weight = ? WHERE artist = ?', (1.0 / count, artist, ))

    def __get_local_file_name(self, filename):
        """
        Returns an MD5 based file name.
        """
        f = open(filename, 'rb')
        m = hashlib.md5()
        while True:
            data = f.read(16384)
            if not data:
                break
            m.update(data)
        name = m.hexdigest() + os.path.splitext(filename)[1].lower()
        return os.path.join(name[0], name[1], name)

    def __get_track_id(self, filename, cur):
        """
        Returns a new track id or the existing one.
        """
        ardj.log.debug('Looking for an id for file %s' % filename)
        row = cur.execute('SELECT id FROM tracks WHERE filename = ?', (filename, )).fetchone()
        if row:
            ardj.log.debug(u'Reusing track id %u.' % row[0])
            return row[0]
        track_id = cur.execute('INSERT INTO tracks (artist) VALUES (NULL)').lastrowid
        ardj.log.debug(u'New track id is %u.' % track_id)
        return track_id

    def __get_track_properties(self, filepath, properties):
        props = {
            'artist': 'Unknown Artist',
            'title': 'Untitled',
            'length': 0,
            'weight': 1.0,
            'count': 0,
        }
        tg = ardj.tags.get(filepath)
        if tg is not None:
            for k in props.keys():
                if k in tg:
                    props[k] = tg[k]
        if type(properties) == dict:
            props.update(properties)
        return props

    def backup_track_data(self, args):
        cur = self.database.cursor()
        filename, artist, title, weight, count, last_played = cur.execute('SELECT filename, artist, title, weight, count, last_played FROM tracks WHERE id = ?', (args['id'], )).fetchone()
        comment = u'ardj=1;weight=%f;count=%u;last_played=%s' % (weight, count, last_played)
        try:
            ardj.tags.set(os.path.join(ardj.settings.get_music_dir(), filename.encode('utf-8')), { 'artist': artist, 'title': title, 'ardj': comment })
        except Exception, e:
            ardj.log.error(u'Could not write metadata to %s: %s' % (filename, e))

    def find(self, pattern):
        """
        Returns tracks matching the pattern.
        """
        if not len(pattern):
            return []
        # Split and filter words.
        words = re.split('\s+', pattern)
        numbers = [w for w in words if w.isdigit()]
        # Basic SQL setup.
        sql = 'SELECT id, filename, artist, title, weight FROM tracks WHERE'
        params = tuple()
        # Process request with numeric values only: exact tracks, even deleted.
        if len(numbers) == len(words):
            sql += ' id IN (%s)' % (', '.join(['?'] * len(numbers)))
            params = tuple(numbers)
        # Process full-text search requests.
        else:
            sql = 'SELECT id, filename, artist, title, weight FROM tracks WHERE weight > 0'
            params = tuple()
            words = u'%' + u' '.join([l for l in re.split('\s+', pattern) if not l.startswith('@')]) + u'%'
            if words != u'%%':
                sql += u' AND (title LIKE ? OR artist LIKE ?)'
                params += (words, words, )
            for label in re.split('\s+', pattern):
                if label.startswith('@'):
                    sql += ' AND id IN (SELECT track_id FROM labels WHERE label = ?)'
                    params += (label[1:], )
        sql += ' ORDER BY id'
        self.database.debug(sql, params)
        cur = self.database.cursor()
        return [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'weight': row[4], 'labels': self.__get_track_labels(row[0], cur) } for row in cur.execute(sql, params).fetchall()]

    def purge(self):
        """
        Removes files that were deleted (zero weight) from the database.
        """
        cur = self.database.cursor()
        musicdir = ardj.settings.get_music_dir()
        for id, filename in [(row[0], os.path.join(musicdir, row[1].encode('utf-8'))) for row in cur.execute('SELECT id, filename FROM tracks WHERE weight = 0').fetchall()]:
            if os.path.exists(filename):
                os.unlink(filename)
        cur.execute('DELETE FROM tracks WHERE weight = 0')
        self.database.purge(cur)

    def __get_track_labels(self, track_id, cur):
        return [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (track_id, )).fetchall()]

def Open():
    global ardj_instance
    if ardj_instance is None:
        ardj_instance = old_ardj()
    return ardj_instance
