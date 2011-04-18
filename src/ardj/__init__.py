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
