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

"""ARDJ, an artificial DJ.

This module contains the database related code.
"""

import logging
import os
import re
import sys
import time
import traceback

try:
    from sqlite3 import dbapi2 as sqlite
    from sqlite3 import OperationalError
except ImportError:
    print >> sys.stderr, 'Please install pysqlite2.'
    sys.exit(13)

import ardj.settings
import ardj.scrobbler
import ardj.util


class Model(dict):
    table_name = None
    fields = ()
    key_name = None

    @classmethod
    def get_by_id(cls, id):
        fields_sql = ", ".join(cls.fields)
        sql = "SELECT %s FROM %s WHERE %s = ?" % (fields_sql, cls.table_name, cls.key_name)
        row = fetchone(sql, (id, ))
        if row is not None:
            return cls._from_row(row)

    @classmethod
    def find_all(cls):
        fields_sql = ", ".join(cls.fields)
        sql = "SELECT %s FROM %s" % (fields_sql, cls.table_name)
        return cls._fetch_rows(sql, ())

    @classmethod
    def _fetch_rows(cls, sql, params):
        rows = fetch(sql, params)
        return [cls._from_row(row) for row in rows]

    @classmethod
    def _from_row(cls, row):
        pairs = [(name, row[idx]) for idx, name in enumerate(cls.fields)]
        return cls(dict(pairs))

    @classmethod
    def _fields_sql(cls):
        return ", ".join(cls.fields)

    @classmethod
    def delete_all(cls):
        """Deletes all records from the table."""
        return execute("DELETE FROM %s" % cls.table_name, ())

    def delete(self):
        sql = "DELETE FROM %s WHERE %s = ?" % (self.table_name, self.key_name)
        execute(sql, (self[self.key_name], ))
        self[self.key_name] = None

    def put(self):
        if self.get(self.key_name) is None:
            return self._insert()
        return self._update()

    def _insert(self):
        fields = [f for f in self.fields if f != self.key_name]
        fields_sql = ", ".join(fields)
        params_sql = ", ".join(["?"] * len(fields))

        sql = "INSERT INTO %s (%s) VALUES (%s)" % (self.table_name, fields_sql, params_sql)
        params = [self.get(field) for field in fields]

        self[self.key_name] = execute(sql, params)
        return self[self.key_name]

    def _update(self):
        fields = [f for f in self.fields if f != self.key_name]
        fields_sql = ", ".join(["%s = ?" for field in fields])

        sql = "UPDATE %s SET %s WHERE %s = ?" % (self.table_name, fields_sql, self.key_name)
        params = [self.get(field) for field in fields] + [self[self.key_name]]

        return execute(sql, params)


class Message(Model):
    """Represents an outgoing XMPP message."""
    table_name = "jabber_messages"
    fields = "id", "message", "re"
    key_name = "id"


class DownloadRequest(Model):
    table_name = "download_queue"
    fields = "artist", "owner"

    @classmethod
    def find_by_artist(cls, artist):
        sql = "SELECT %s FROM %s WHERE artist = ?" % (cls._fields_sql(), cls.table_name)
        return cls._fetch_rows(sql, (artist, ))

    @classmethod
    def get_one(cls):
        """Returns one random download ticket."""
        sql = "SELECT %s FROM %s LIMIT 1" % (cls._fields_sql(), cls.table_name)
        rows = cls._fetch_rows(sql, ())
        if rows:
            return rows[0]


class Track(Model):
    """Stores information about a track."""
    table_name = "tracks"
    fields = "id", "artist", "title", "filename", "length", "weight", "real_weight", "count", "last_played", "owner"
    key_name = "id"

    @classmethod
    def find_all(cls):
        """Returns all tracks with positive weight."""
        sql = "SELECT %s FROM %s WHERE weight > 0" % (self._fields_sql(), self.table_name)
        return self._fetch_rows(sql, ())

    @classmethod
    def get_artist_names(cls):
        """Returns all artist names."""
        return fetchcol("SELECT DISTINCT artist FROM %s" % self.table_name)

    @classmethod
    def rename_artist(cls, old_name, new_name):
        """Renames an artist."""
        sql = "UPDATE %s SET artist = ? WHERE artist = ?" % (self.table_name, new_name, old_name)
        execute(sql, ())

    @classmethod
    def find_without_lastfm_tags(cls):
        sql = "SELECT %s FROM %s WHERE weight > 0 AND id NOT IN (SELECT track_id FROM labels WHERE label LIKE 'lastfm:%%') ORDER BY id" % (cls._fields_sql(), cls.table_name)
        return cls._fetch_rows(sql, ())

    def get_labels(self):
        if not self.get(self.key_name):
            return []
        return fetchcol("SELECT label FROM labels WHERE track_id = ?", (self[self.key_name], ))

    def set_labels(self, labels):
        if type(labels) != list:
            raise TypeError("Labels must be a list.")

        execute("DELETE FROM labels WHERE track_id = ?", (self["id"], ))
        for tag in list(set(labels)):
            execute("INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)", (self["id"], tag, "unknown", ))

        logging.debug("New labels for track %u: %s" % (self["id"], labels))

    def get_average_length(self):
        """Returns average track length in minutes."""
        s_prc = s_qty = 0.0
        for prc, qty in self.fetch("SELECT ROUND(length / 60) AS r, COUNT(*) FROM tracks GROUP BY r"):
            s_prc += prc * qty
            s_qty += qty
        return int(s_prc / s_qty * 60 * 1.5)


class Queue(Model):
    """Stores information about a track to play out of regular order."""
    table_name = "queue"
    fields = "id", "track_id", "owner"
    key_name = "id"


def get_init_statements(dbtype):
    """Returns a list of SQL statements to initialize the database."""
    paths = []
    paths.append(os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "../share/database")))
    paths.append("/usr/local/share/ardj/database")
    paths.append("/usr/share/ardj/database")
    for path in paths:
        filename = os.path.join(path, dbtype + ".sql")
        if os.path.exists(filename):
            lines = file(filename, "rb").read().decode("utf-8").strip().split("\n")
            return [line for line in lines if line.strip() and not line.startswith("--")]
    return []


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

    def __del__(self):
        self.commit()
        logging.debug(u'Database closed.')

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            filename = ardj.settings.getpath2("database_path", "database/local")
            if filename is None:
                raise Exception('This ardj instance does not have a local database (see the database_path config option).')
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
        stack = "".join(traceback.format_stack()[-5:-1])
        #logging.debug("Starting a transaction (returning a cursor)\n%s" % stack)
        return self.db.cursor()

    def commit(self):
        """Commits current transaction, for internal use. """
        self.db.commit()

    def rollback(self):
        """Cancel pending changes."""
        logging.debug("Rolling back a transaction.")
        self.db.rollback()

    def fetch(self, sql, params=None):
        return self.execute(sql, params, fetch=True)

    def execute(self, sql, params=None, fetch=False):
        cur = self.db.cursor()
        try:
            args = [sql]
            if params is not None:
                args.append(params)
            cur.execute(*args)
            if fetch:
                return cur.fetchall()
            elif sql.startswith("INSERT "):
                return cur.lastrowid
            else:
                return cur.rowcount
        except Exception, e:
            logging.error("Failed SQL statement: %s, params: %s" % (sql, params))
            raise e
        finally:
            cur.close()

    def update(self, table, args):
        """Performs update on a label.

        Updates the table with values from the args dictionary, key "id" must
        identify the record.  Example:

        db.update('tracks', {'weight': 1, 'id': 123})
        """
        sql = []
        params = []
        for k in args:
            if k != 'id':
                sql.append(k + ' = ?')
                params.append(args[k])
        params.append(args['id'])

        self.execute('UPDATE %s SET %s WHERE id = ?' % (table, ', '.join(sql)), tuple(params))

    def debug(self, sql, params, quiet=False):
        """Logs the query in human readable form.

        Replaces question marks with parameter values (roughly)."""
        for param in params:
            param = unicode(param)
            if param.isdigit():
                sql = sql.replace(u'?', param, 1)
            else:
                sql = sql.replace(u'?', u"'" + param + u"'", 1)
        logging.debug(u'SQL: ' + sql)
        return sql

    def merge_aliases(self):
        """Moves votes from similar accounts to one."""
        for k, v in ardj.settings.get2("jabber_aliases", "jabber/aliases", {}).items():
            for alias in v:
                self.execute('UPDATE votes SET email = ? WHERE email = ?', (k, alias, ))

    def purge(self):
        """Removes stale data.

        Stale data in queue items, labels and votes linked to tracks that no
        longer exist.  In addition to deleting such links, this function also
        analyzed all tables (to optimize indexes) and vacuums the database.
        """
        old_size = os.stat(self.filename).st_size
        self.merge_aliases()
        self.execute('DELETE FROM queue WHERE track_id NOT IN (SELECT id FROM tracks)')
        self.execute('DELETE FROM labels WHERE track_id NOT IN (SELECT id FROM tracks)')
        self.execute('DELETE FROM votes WHERE track_id NOT IN (SELECT id FROM tracks)')
        for table in ('playlists', 'tracks', 'queue', 'urgent_playlists', 'labels', 'karma'):
            self.execute('ANALYZE ' + table)
        self.execute('VACUUM')
        logging.info('%u bytes saved after database purge.' % (os.stat(self.filename).st_size - old_size))

    def mark_hitlist(self):
        """Marks best tracks with the "hitlist" label.

        Only processes tracks labelled with "music".  Before applying the
        label, removes it from the tracks that have it already."""
        set_label, check_label = 'hitlist', 'music'

        self.execute('DELETE FROM labels WHERE label = ?', (set_label, ))

        weight = fetchone('SELECT real_weight FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY real_weight DESC LIMIT 19, 1', (check_label, ))
        if weight:
            self.execute('INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE real_weight >= ? AND id IN (SELECT track_id FROM labels WHERE label = ?)', (set_label, 'ardj', weight[0], check_label, ))

            lastfm = ardj.scrobbler.LastFM()
            lastfm.authorize()

            for artist, title in self.fetch('SELECT t.artist, t.title FROM tracks t INNER JOIN labels l ON l.track_id = t.id WHERE l.label = ?', (set_label, )):
                lastfm.love(artist, title)

    def mark_recent_music(self):
        """Marks last 100 tracks with "recent"."""
        self.execute('DELETE FROM labels WHERE label = ?', ('recent', ))
        self.execute('INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY id DESC LIMIT 100', ('recent', 'ardj', 'music', ))

        self.execute('DELETE FROM labels WHERE label = ?', ('fresh', ))
        count = self.execute('INSERT INTO labels (track_id, label, email) SELECT id, ?, ? FROM tracks WHERE count < 10 AND weight > 0 AND id IN (SELECT track_id FROM labels WHERE label = ?)', ('fresh', 'ardj', 'music', ))
        print 'Found %u fresh songs.' % count

    def mark_orphans(self, set_label='orphan', quiet=False):
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

        self.execute('DELETE FROM labels WHERE label = ?', (set_label, ))

        sql = 'SELECT id, artist, title FROM tracks WHERE weight > 0 AND id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY artist, title' % ', '.join(['?'] * len(used_labels))
        rows = self.fetch(sql, used_labels)

        if rows:
            if not quiet:
                print '%u orphan tracks found:' % len(rows)
            for row in rows:
                if not quiet:
                    print '%8u; %s -- %s' % (row[0], (row[1] or 'unknown').encode('utf-8'), (row[2] or 'unknown').encode('utf-8'))
                self.execute('INSERT INTO labels (track_id, email, label) VALUES (?, ?, ?)', (int(row[0]), 'ardj', set_label))
            return True

    def get_artist_names(self, label=None, weight=0):
        if label is None:
            rows = self.fetch("SELECT DISTINCT artist FROM tracks WHERE weight > ?", (weight, ))
        else:
            rows = self.fetch("SELECT DISTINCT artist FROM tracks WHERE weight > ? AND id IN (SELECT track_id FROM labels WHERE label = ?)", (weight, label, ))
        return [r[0] for r in rows]


def Open(filename=None):
    """Returns the active database instance."""
    return database.get_instance()


def commit():
    # ts = time.time()
    # logging.debug("Commit.")
    Open().commit()
    # logging.debug("Commit took %s seconds." % (time.time() - ts))


def rollback():
    Open().rollback()


def fetch(sql, params=None):
    return Open().fetch(sql, params)


def fetchone(sql, params=None):
    result = fetch(sql, params)
    if result:
        return result[0]


def fetchcol(sql, params=None):
    """Returns a list of first column values."""
    rows = fetch(sql, params)
    if rows:
        return [row[0] for row in rows]


def execute(*args, **kwargs):
    return Open().execute(*args, **kwargs)


def init_sqlite(statements):
    db = Open()
    cur = db.cursor()
    for statement in statements:
        cur.execute(statement)
    db.commit()


def cli_init(args=None):
    """Initializes the database."""
    statements = get_init_statements("sqlite")
    init_sqlite(statements)
    return True
