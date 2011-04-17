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
import ardj.tracks
import ardj.util

ardj_instance = None

class old_ardj:
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
        return ardj.tracks.get_track_by_id(rows[0][0], cur)

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
            return ardj.tracks.get_track_by_id(id, cur)

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

    def __get_track_labels(self, track_id, cur):
        return [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (track_id, )).fetchall()]
