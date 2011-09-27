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
    print >>sys.stderr, 'Please install pysqlite2.'
    sys.exit(13)

import ardj.settings
import ardj.scrobbler
import ardj.tracks
import ardj.util

class database:
    """
    Interface to the database.
    """
    instance = None

    def __init__(self, filename):
        """
        Opens the database, creates tables if necessary.
        """
        self.filename = filename
        isnew = not os.path.exists(self.filename)
        try:
            self.db = sqlite.connect(self.filename, check_same_thread=False)
        except Exception, e:
            logging.error('Could not open database %s: %s' % (filename, e))
            raise

        self.db.create_collation('UNICODE', ardj.util.ucmp)
        self.db.create_function('ULIKE', 2, self.sqlite_ulike)

        cur = self.db.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT, last_played INTEGER)')
        cur.execute('CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, owner TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, weight REAL, real_weight REAL, count INTEGER, last_played INTEGER)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_owner ON tracks (owner)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_weight ON tracks (weight)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_real_weight ON tracks (real_weight)')
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
        cur.execute('CREATE TABLE IF NOT EXISTS votes (track_id INTEGER NOT NULL, email TEXT NOT NULL, vote INTEGER, weight REAL, ts INTEGER)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_track_id ON votes (track_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_email ON votes (email)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_ts ON votes (ts)')
        # карма
        cur.execute('CREATE TABLE IF NOT EXISTS karma (email TEXT, weight REAL)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_karma_email ON karma (email)')
        # лог проигрываний
        cur.execute('CREATE TABLE IF NOT EXISTS playlog (ts INTEGER NOT NULL, track_id INTEGER NOT NULL, listeners INTEGER NOT NULL, lastfm INTEGER NOT NULL DEFAULT 0)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_playlog_ts ON playlog (ts)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_playlog_track_id ON playlog (track_id)')
        # исходящие сообщения
        cur.execute('CREATE TABLE IF NOT EXISTS jabber_messages (id INTEGER PRIMARY KEY, re TEXT, message TEXT)')
        # музыка для загрузки
        cur.execute('CREATE TABLE IF NOT EXISTS download_queue (artist TEXT PRIMARY KEY, owner TEXT)')
        # View для подсчёта веса дорожек на основании кармы.
        # weight = max(0.1, 1 + sum(vote * weight))
        cur.execute('CREATE VIEW IF NOT EXISTS track_weights AS SELECT v.track_id AS track_id, COUNT(*) AS count, MAX(0.1, 1 + SUM(v.vote * k.weight)) AS weight FROM votes v INNER JOIN karma k ON k.email = v.email GROUP BY v.track_id')

    def __del__(self):
        self.commit()
        logging.debug(u'Database closed.')

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            filename = ardj.settings.getpath('database/local')
            if filename is None:
                raise Exception('This ardj instance does not have a local database (see database/local config option).')
            cls.instance = cls(filename)
        return cls.instance

    def sqlite_ulike(self, a, b):
        if a is None or b is None:
            return None
        if ardj.util.lower(b) in ardj.util.lower(a):
            return 1
        return 0

    def cursor(self):
        """Returns a new SQLite cursor, for internal use."""
        return self.db.cursor()

    def commit(self):
        """Commits current transaction, for internal use. """
        self.db.commit()

    def rollback(self):
        """Cancel pending changes."""
        self.db.rollback()

    def update(self, table, args, cur=None):
        """Performs update on a label.

        Updates the table with values from the args dictionary, key "id" must
        identify the record.  Example:

        db.update('tracks', { 'weight': 1, 'id': 123 })
        """
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

    def debug(self, sql, params, quiet=False):
        """Logs the query in human readable form.

        Replaces question marks with parameter values (roughly)."""
        for param in params:
            param = unicode(param)
            if param.isdigit():
                sql = sql.replace(u'?', param, 1)
            else:
                sql = sql.replace(u'?', u"'" + param + u"'", 1)
        logging.debug(u'SQL: ' + sql, quiet=quiet)
        return sql

    def merge_aliases(self, cur=None):
        """Moves votes from similar accounts to one."""
        cur = cur or self.cursor()
        for k, v in ardj.settings.get('jabber/aliases', {}).items():
            for alias in v:
                cur.execute('UPDATE votes SET email = ? WHERE email = ?', (k, alias, ))


    def purge(self, cur=None):
        """Removes stale data.

        Stale data is queue items, labels and votes linked to tracks that no
        longer exist.  In addition to deleting such links, this function also
        analyzed all tables (to optimize indexes) and vacuums the database.
        """
        old_size = os.stat(self.filename).st_size
        cur = cur or self.cursor()
        self.merge_aliases(cur)
        cur.execute('DELETE FROM queue WHERE track_id NOT IN (SELECT id FROM tracks)')
        cur.execute('DELETE FROM labels WHERE track_id NOT IN (SELECT id FROM tracks)')
        cur.execute('DELETE FROM votes WHERE track_id NOT IN (SELECT id FROM tracks)')
        for table in ('playlists', 'tracks', 'queue', 'urgent_playlists', 'labels', 'karma'):
            cur.execute('ANALYZE ' + table)
        cur.execute('VACUUM')
        logging.info('%u bytes saved after database purge.' % (os.stat(self.filename).st_size - old_size))

    def mark_hitlist(self, cur=None):
        """Marks best tracks with the "hitlist" label.

        Only processes tracks labelled with "music".  Before applying the
        label, removes it from the tracks that have it already."""
        set_label, check_label = 'hitlist', 'music'

        cur = cur or self.cursor()
        cur.execute('DELETE FROM labels WHERE label = ?', (set_label, ))

        weight = cur.execute('SELECT real_weight FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY real_weight DESC LIMIT 19, 1', (check_label, )).fetchone()
        if weight:
            cur.execute('INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE real_weight >= ? AND id IN (SELECT track_id FROM labels WHERE label = ?)', (set_label, 'ardj', weight[0], check_label, ))

            lastfm = ardj.scrobbler.LastFM()
            lastfm.authorize()

            for artist, title in cur.execute('SELECT t.artist, t.title FROM tracks t INNER JOIN labels l ON l.track_id = t.id WHERE l.label = ?', (set_label, )).fetchall():
                lastfm.love(artist, title)

    def mark_recent_music(self, cur=None):
        """Marks last 100 tracks with "recent"."""
        cur = cur or self.cursor()

        cur.execute('DELETE FROM labels WHERE label = ?', ('recent', ))
        cur.execute('INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY id DESC LIMIT 100', ('recent', 'ardj', 'music', ))

        cur.execute('DELETE FROM labels WHERE label = ?', ('fresh', ))
        cur.execute('INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE count < 10 AND weight > 0 AND id IN (SELECT track_id FROM labels WHERE label = ?)', ('fresh', 'ardj', 'music', ))
        print 'Found %u fresh songs.' % cur.rowcount

    def mark_preshow_music(self, cur=None):
        """Marks music liked by all show hosts with "preshow-music"."""
        common_label, set_label = 'music', 'preshow-music'
        users = ardj.settings.get('live/hosts')
        if users is None:
            logging.warning('Could not mark preshow-music: live/hosts not set.')
            return

        cur = cur or self.cursor()
        cur.execute('DELETE FROM labels WHERE label = ?', (set_label, ))

        sql = 'INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?)'
        params = (set_label, 'robot', common_label, )
        for user in users:
            sql += ' AND id IN (SELECT track_id FROM votes WHERE vote > 0 AND email = ?)'
            params += (user, )
        cur.execute(sql, params)

    def get_stats(self, cur=None):
        """Returns database statistics.
        
        Returns information about the database in the form of a
        dictionary with the following keys: tracks, seconds."""
        count, length = 0, 0
        cur = cur or self.cursor()
        for row in cur.execute('SELECT length FROM tracks WHERE weight > 0').fetchall():
            count = count + 1
            if row[0] is not None:
                length = length + row[0]
        return { 'tracks': count, 'seconds': length }

    def mark_orphans(self, set_label='orphan', cur=None, quiet=False):
        """Labels orphan tracks with "orphan".

        Orphans are tracks that don't belong to a playlist."""
        used_labels = []
        for playlist in ardj.settings.load().get_playlists():
            if 'labels' in playlist:
                labels = playlist['labels']
            else:
                labels = [playlist['name']]
            used_labels += [l for l in labels if not l.startswith('-')]
        used_labels = list(set(used_labels))

        if not(used_labels):
            logging.warning('Could not mark orphan tracks: no labels are used in playlists.yaml')
            return False

        cur = cur or self.cursor()
        cur.execute('DELETE FROM labels WHERE label = ?', (set_label, ))

        sql = 'SELECT id, artist, title FROM tracks WHERE weight > 0 AND id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY artist, title' % ', '.join(['?'] * len(used_labels))
        cur.execute(sql, used_labels)
        rows = cur.fetchall()

        if rows:
            if not quiet:
                print '%u orphan tracks found:' % len(rows)
            for row in rows:
                if not quiet:
                    print '%8u; %s -- %s' % (row[0], (row[1] or 'unknown').encode('utf-8'), (row[2] or 'unknown').encode('utf-8'))
                cur.execute('INSERT INTO labels (track_id, email, label) VALUES (?, ?, ?)', (int(row[0]), 'ardj', set_label))
            return True

    def mark_long(self):
        """Marks unusuall long tracks."""
        cur = self.cursor()
        length = ardj.tracks.get_average_length(cur)
        cur.execute('DELETE FROM labels WHERE label = \'long\'')
        cur.execute('INSERT INTO labels (track_id, email, label) SELECT id, \'ardj\', \'long\' FROM tracks WHERE length > ?', (length, ))
        count = cur.execute('SELECT COUNT(*) FROM labels WHERE label = \'long\'').fetchone()[0]
        print 'Average length is %u seconds, %u tracks match.' % (length, count)

    def get_artist_names(self, label=None, weight=0, cur=None):
        cur = cur or self.cursor()
        if label is None:
            cur.execute("SELECT DISTINCT artist FROM tracks WHERE weight > ?", (weight, ))
        else:
            cur.execute("SELECT DISTINCT artist FROM tracks WHERE weight > ? AND id IN (SELECT track_id FROM labels WHERE label = ?)", (weight, label, ))
        return [r[0] for r in cur.fetchall()]

    def fix_artist_names(self):
        """Corrects artist names according to LastFM."""
        cli = ardj.scrobbler.LastFM().authorize()

        cur = self.cursor()
        names = self.get_artist_names('music', cur=cur)
        print 'Checking %u artists.' % len(names)

        for name in names:
            new_name = cli.get_corrected_name(name)
            if new_name is not None and new_name != name:
                logging.info(u'Correcting "%s" to "%s"' % (name, new_name))
                cur.execute('UPDATE tracks SET artist = ? WHERE artist = ?', (new_name, name, ))


def Open(filename=None):
    """Returns the active database instance."""
    return database.get_instance()


def cursor():
    return Open().cursor()


def commit():
    Open().commit()


def pick_jingle(cur, label):
    """Returns a jingle with the specified label."""
    row = cur.execute('SELECT track_id FROM labels WHERE label = ? ORDER BY RANDOM() LIMIT 1', (label, )).fetchone()
    if row:
        return row[0]


def queue_tracks(cur, track_ids):
    """Queues all specified tracks."""
    for track_id in track_ids:
        cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track_id, 'robot', ))


USAGE = """Usage: ardj db commands...

Commands:
  console           -- open SQLite console
  fix-artist-names  -- correct artist names according to last.fm
  flush-queue       -- remove everything from queue
  import            -- add tracks from a public "drop box"
  mark-hitlist      -- mark best tracks with "hitlist"
  mark-orphans      -- mark tracks that don't belong to a playlist
  mark-preshow      -- marks preshow music
  mark-recent       -- mark last 100 tracks with "recent"
  purge             -- remove dead data
  stat              -- show database statistics
  """


def merge_votes(args):
    """Collapses votes according to jabber/aliases."""
    db = Open()
    db.merge_aliases()
    db.commit()


def run_cli(args):
    """Implements the "ardj db" command."""
    db = Open()
    ok = False
    if 'console' in args or not args:
        ardj.util.run([ 'sqlite3', '-header', db.filename ])
        ok = True
    if 'flush-queue' in args:
        db.cursor().execute('DELETE FROM queue')
        ok = True
    if 'mark-hitlist' in args:
        db.mark_hitlist()
        ok = True
    if 'mark-preshow' in args:
        db.mark_preshow_music()
        ok = True
    if 'mark-recent' in args:
        db.mark_recent_music()
        ok = True
    if 'mark-orphans' in args:
        db.mark_orphans()
        ok = True
    if 'mark-long' in args:
        db.mark_long()
        ok = True
    if 'purge' in args:
        db.purge()
        ok = True
    if 'stat' in args:
        stats = db.get_stats()
        print '%u tracks, %.1f hours.' % (stats['tracks'], stats['seconds'] / 60 / 60)
        ok = True
    if 'fix-artist-names' in args:
        db.fix_artist_names()
        ok = True
    if not ok:
        print USAGE
    else:
        db.commit()
