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

This module contains the database related code.  It currently is a mixture of
hand-made SQLite code and some new StORM based parts.  Later everything will be
moved to StORM.
"""

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

from storm.locals import *  # https://storm.canonical.com

import ardj.settings
import ardj.scrobbler
import ardj.tracks
import ardj.util


class _store:
    _db = None
    _store = None

    @classmethod
    def init(cls):
        if cls._store is None:
            cls._db = create_database(ardj.settings.get("database_uri"))
            cls._store = Store(cls._db)

    @classmethod
    def get(cls):
        """Contains an instance of a store, to access the databse.

        This is a read-only property."""
        cls.init()
        return cls._store

    @classmethod
    def get_db(cls):
        cls.init()
        return cls._db


class Model(object):
    _db = None
    _store = None

    @classmethod
    def _get_store(cls):
        if Model._store is None:
            Model._db = create_database(ardj.settings.get("database_uri"))
            Model._store = Store(Model._db)
        return Model._store

    @classmethod
    def create(cls, *args, **kwargs):
        _tmp = cls(*args, **kwargs)
        cls._get_store().add(_tmp)
        return _tmp

    @classmethod
    def find_all(cls):
        return cls._get_store().find(cls)

    def delete(self):
        return self._get_store().remove(self)


class Message(Model):
    """Used for storing outgoing XMPP messages.  When you need to send an XMPP
    message, create a Message instance and save it.

    Data:
    re -- recipient JID
    text -- message text
    """

    __storm_table__ = "jabber_messages"
    id = Int(primary=True)
    re = Unicode()
    message = Unicode()

    def __init__(self, message, re=None):
        if re is not None:
            re = unicode(re)
        self.re = re
        self.message = unicode(message)


class ArtistDownloadRequest(Model):
    """Stores a request to download more tracks by the specified artist.

    Data:
    artist -- artist name
    """

    __storm_table__ = "download_queue"
    artist = Unicode(primary=True)
    owner = Unicode()

    def __init__(self, artist, owner=None):
        if owner is not None:
            owner = unicode(owner)
        self.artist = unicode(artist)
        self.owner = owner

    @classmethod
    def find_by_artist(cls, artist):
        """Returns a request for artist with the specified name.  If there's no
        such request, returns None."""
        return cls._get_store().find(cls, cls.artist == unicode(artist)).one()

    @classmethod
    def get_one(cls):
        """Returns one random download ticket."""
        return cls._get_store().find(cls)[:1].one()


class Track(Model):
    """Stores information about a track."""
    __storm_table__ = "tracks"

    id = Int(primary=True)
    artist = Unicode()
    title = Unicode()
    filename = Unicode()
    length = Int()
    weight = Float()
    real_weight = Float()
    count = Int()
    last_played = Int()
    owner = Unicode()

    def __init__(self, artist, title, filename, length=0, weight=1.0, real_weight=1.0, count=0, last_played=None, owner=None):
        self.artist = unicode(artist)
        self.title = unicode(title)
        self.filename = unicode(filename)
        self.length = length
        self.weight = weight
        self.real_weight = real_weight
        self.count = count
        self.last_played = last_played
        if owner is not None:
            self.owner = unicode(owner)

    @classmethod
    def find_all(cls):
        """Returns all tracks with positive weight."""
        return cls._get_store().find(cls, cls.weight > 0)


class Queue(Model):
    """Stores information about a track to play ASAP."""
    __storm_table__ = "queue"
    id = Int(primary=True)
    track_id = Int()
    owner = Unicode()

    def __init__(self, track_id, owner):
        self.track_id = int(track_id)
        self.owner = unicode(owner)


def get_init_statements(dbtype):
    """Returns a list of SQL statements to initialize the database."""
    paths = []
    paths.append(os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "../share/database")))
    paths.append("/usr/local/share/ardj/database")
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

        Stale data in queue items, labels and votes linked to tracks that no
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
    Model._get_store().commit()
    Open().commit()


USAGE = """Usage: ardj db commands...

Commands:
  console           -- open SQLite console
  fix-artist-names  -- correct artist names according to last.fm
  mark-hitlist      -- mark best tracks with "hitlist"
  mark-orphans      -- mark tracks that don't belong to a playlist
  mark-preshow      -- marks preshow music
  mark-recent       -- mark last 100 tracks with "recent"
  purge             -- remove dead data
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
    if 'fix-artist-names' in args:
        db.fix_artist_names()
        ok = True
    if not ok:
        print USAGE
    else:
        db.commit()


def cli_init(args):
    """Initializes the database."""
    db = Open()
    cur = db.cursor()
    store = _store.get()
    for statement in get_init_statements("sqlite"):
        cur.execute(statement)
        store.execute(statement)
    db.commit()
    store.commit()
    return True
