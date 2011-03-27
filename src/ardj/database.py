# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:
#
# database related functions for ardj.
#
# ardj is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# ardj is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import re
import sys
import time

try:
    from sqlite3 import dbapi2 as sqlite
    from sqlite3 import OperationalError
except ImportError:
    logging.critical(u'Please install pysqlite2.')
    sys.exit(13)

import ardj.settings

class database:
    """
    Interface to the database.
    """
    def __init__(self, filename):
        """
        Opens the database, creates tables if necessary.
        """
        self.filename = filename
        isnew = not os.path.exists(self.filename)
        self.db = sqlite.connect(self.filename, check_same_thread=False)
        self.db.create_function('randomize', 4, self.sqlite_randomize)
        cur = self.db.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT, last_played INTEGER)')
        cur.execute('CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, owner TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, artist_weight REAL, weight REAL, count INTEGER, last_played INTEGER)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_owner ON tracks (owner)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')
        cur.execute('CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY, track_id INTEGER, owner TEXT)')
        # экстренный плейлист
        cur.execute('CREATE TABLE IF NOT EXISTS urgent_playlists (labels TEXT, expires INTEGER)')
        cur.execute('CREATE INDEX IF NOT EXISTS urgent_playlists_expires ON urgent_playlists (expires)')
        # метки
        cur.execute('CREATE TABLE IF NOT EXISTS labels (track_id INTEGER NOT NULL, email TEXT NOT NULL, label TEXT NOT NULL)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_labels_track_id ON labels (track_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_labels_email ON labels (email)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_labels_label ON labels (label)')
        # голоса пользователей
        cur.execute('CREATE TABLE IF NOT EXISTS votes (track_id INTEGER NOT NULL, email TEXT NOT NULL, vote INTEGER, weight REAL)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_track_id ON votes (track_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_email ON votes (email)')
        # карма
        cur.execute('CREATE TABLE IF NOT EXISTS karma (email TEXT, weight REAL)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_karma_email ON karma (email)')
        # View для подсчёта веса дорожек на основании кармы.
        # weight = max(0.1, 1 + sum(vote * weight))
        cur.execute('CREATE VIEW IF NOT EXISTS track_weights AS SELECT v.track_id AS track_id, COUNT(*) AS count, MAX(0.1, 1 + SUM(v.vote * k.weight)) AS weight FROM votes v INNER JOIN karma k ON k.email = v.email GROUP BY v.track_id')

    def __del__(self):
        self.commit()
        logging.info(u'Database closed.')

    def sqlite_randomize(self, id, artist_weight, weight, count):
        """
        The randomize() function for SQLite.
        """
        result = weight or 0
        if artist_weight is not None:
            result = result * artist_weight
        # result = result / ((count or 0) + 1)
        result = min(max(0.1, result), 2.0)
        return result

    def cursor(self):
        """
        Returns a new SQLite cursor, for internal use.
        """
        return self.db.cursor()

    def commit(self):
        """
        Commits current transaction, for internal use.
        """
        self.db.commit()

    def rollback(self):
        """
        Cancel pending changes.
        """
        self.db.rollback()

    def update(self, table, args, cur=None):
        if cur is None:
            cur = self.cursor()

        sql = []
        params = []
        for k in args:
            if k != 'id':
                sql.append(k + ' = ?')
                params.append(args[k])
        params.append(args['id'])

        cur.execute('UPDATE %s SET %s WHERE id = ?' % (table, ', '.join(sql)), tuple(params))

    def add_vote(self, track_id, email, vote):
        """Adds a vote for/against a track, returns track's current weight.

        The process is: 1) add a record to the votes table, 2) update email's
        record in the karma table, 3) update weight for all tracks email voted
        for/against.

        Votes other than +1 and -1 are skipped.
        """
        cur = self.cursor()

        # Normalize the vote.
        if vote > 0: vote = 1
        elif vote < 0: vote = -1

        # Skip wrong values.
        cur.execute('DELETE FROM votes WHERE track_id = ? AND email = ?', (track_id, email, ))
        if vote != 0:
            cur.execute('INSERT INTO votes (track_id, email, vote) VALUES (?, ?, ?)', (track_id, email, vote, ))

        # Update email's karma.
        all = float(cur.execute('SELECT COUNT(*) FROM votes').fetchall()[0][0])
        his = float(cur.execute('SELECT COUNT(*) FROM votes WHERE email = ?', (email, )).fetchall()[0][0])
        value = 0.25 # his / all
        cur.execute('DELETE FROM karma WHERE email = ?', (email, ))
        cur.execute('INSERT INTO karma (email, weight) VALUES (?, ?)', (email, value, ))

        # Update all track weights.  Later this can be replaced with joins and
        # views (when out of beta).
        ## wtf ?! ## cur.execute('UPDATE tracks SET weight = 1')
        result = 1
        for row in cur.execute('SELECT track_id, weight FROM track_weights WHERE track_id IN (SELECT track_id FROM votes WHERE email = ?) OR track_id = ?', (email, track_id, )).fetchall():
            cur.execute('UPDATE tracks SET weight = ? WHERE id = ?', (row[1], row[0], ))
            if track_id == row[0]:
                result = row[1]

        self.commit()
        return result

    def add_labels(self, track_id, email, labels):
        """Adds labels to a track.  Labels prefixed with a dash are removed.
        """
        cur = self.cursor()
        for label in labels:
            neg = label.startswith('-')
            if neg:
                label = label[1:]
            if label.startswith('@'):
                label = label[1:]
            if neg:
                cur.execute('DELETE FROM labels WHERE track_id = ? AND label = ?', (track_id, label, ))
            elif not cur.execute('SELECT 1 FROM labels WHERE track_id = ? AND label = ?', (track_id, label, )).fetchall():
                cur.execute('INSERT INTO labels (track_id, email, label) VALUES (?, ?, ?)', (track_id, email, label, ))
        current = [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (track_id, )).fetchall()]
        self.commit()
        return current

    def set_urgent(self, labels, expires=None):
        """
        Sets music filter to be used for picking random tracks.  If set, only
        matching tracks will be played, regardless of playlists.yaml.  Labels
        must be specified as a string, using spaces or commas as separators.
        Use "all" to reset.
        """
        cur = self.cursor()
        cur.execute('DELETE FROM urgent_playlists')
        if labels != 'all':
            if expires is None:
                expires = time.time() + 3600
            cur.execute('INSERT INTO urgent_playlists (labels, expires) VALUES (?, ?)', (labels, int(expires), ))
        self.commit()

    def get_urgent(self):
        """
        Returns current playlist preferences.
        """
        data = self.cursor().execute('SELECT labels FROM urgent_playlists WHERE expires > ? ORDER BY expires', (int(time.time()), )).fetchall()
        if data:
            return re.split('[,\s]+', data[0][0])
        return None

    def update_track(self, properties, cur=None):
        """
        Updates valid track attributes.
        """
        if type(properties) != dict:
            raise Exception('Track properties must be passed as a dictionary.')
        if not properties.has_key('id'):
            raise Exception('Track properties have no id.')
        cur = cur or self.cursor()

        sql = []
        params = []
        for k in properties:
            if k in ('filename', 'artist', 'title', 'length', 'artist_weight', 'weight', 'count', 'last_played', 'owner'):
                sql.append(k + ' = ?')
                params.append(properties[k])

        if not sql:
            logging.debug('No fields to update.')
        else:
            params.append(properties['id'])
            sql = 'UPDATE tracks SET ' + ', '.join(sql) + ' WHERE id = ?'
            self.debug(sql, params)
            cur.execute(sql, tuple(params))

        if properties.has_key('labels') and type(properties['labels']) == list and properties.has_key('owner'):
            for label in properties['labels']:
                sql = 'INSERT INTO labels (track_id, email, label) VALUES (?, ?, ?)'
                params = (properties['id'], properties['owner'], label, )
                self.debug(sql, params)
                cur.execute(sql, params)

    def debug(self, sql, params):
        for param in params:
            param = unicode(param)
            if param.isdigit():
                sql = sql.replace(u'?', param, 1)
            else:
                sql = sql.replace(u'?', u"'" + param + u"'", 1)
        logging.debug(u'SQL: ' + sql)

    def purge(self, cur=None):
        """
        Removes stale data.
        """
        cur = cur or self.cursor()
        cur.execute('DELETE FROM queue WHERE track_id NOT IN (SELECT id FROM tracks)')
        cur.execute('DELETE FROM labels WHERE track_id NOT IN (SELECT id FROM tracks)')
        cur.execute('DELETE FROM votes WHERE track_id NOT IN (SELECT id FROM tracks)')
        for table in ('playlists', 'tracks', 'queue', 'urgent_playlists', 'labels', 'karma'):
            cur.execute('ANALYZE ' + table)
        cur.execute('VACUUM')

    def queue_track(self, track_id, robot_name=None, cursor=None, commit=True):
        cur = cur or self.cursor()
        cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (int(track_id), robot_name or 'a robot', ))
        if commit:
            self.commit()

instance = None
def Open(filename=None):
    global instance
    if instance is None:
        if filename is None:
            filename = ardj.settings.getpath('database', '~/.config/ardj/ardj.sqlite')
        instance = database(filename)
    return instance
