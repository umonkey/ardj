import os
import unittest

import ardj.database


class TestCase(unittest.TestCase):
    tables = []

    def __init__(self):
        unittest.TestCase.__init__(self)
        self.db = None
        self.cur = None

    def runTest(self):
        pass

    def setUp(self):
        self.db = ardj.database.Open()
        self.cur = self.db.cursor()

        for table in self.tables:
            self.check_table_size(self.cur, table)

    def tearDown(self):
        self.db.rollback()

        for table in self.tables:
            self.check_table_size(self.cur, table)

    def check_table_size(self, cur, name, wanted=0):
        size = cur.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        self.assertEquals(wanted, size, 'table %s has %u records instead of %u.' % (name, size, wanted))


class Open(TestCase):
    def runTest(self):
        self.assertEquals('unittests/data/database.sqlite', self.db.filename)


class Transactions(TestCase):
    tables = ['queue']

    def runTest(self):
        self.cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (0, 'test', ))
        self.assertEquals(1, self.cur.execute('SELECT COUNT(*) FROM queue').fetchone()[0], 'Failed to insert a record into queue.')


class Update(TestCase):
    def runTest(self):
        self.cur.execute('DELETE FROM queue')
        row = self.cur.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (1, 'ardj', )).lastrowid
        self.assertEquals(row, 1)

        self.db.update('queue', { 'owner': 'test', 'id': row })
        tmp = self.cur.execute('SELECT * FROM queue').fetchone()
        self.assertEquals(tmp, (1, 1, 'test'))


class Debug(TestCase):
    def runTest(self):
        sql = self.db.debug('SELECT ?, ?', (1, 2, ), quiet=True)
        self.assertEquals('SELECT 1, 2', sql)


class RecentMarker(TestCase):
    tables = ['tracks', 'labels']

    def runTest(self):
        for idx in range(200):
            row = self.cur.execute('INSERT INTO tracks (title) VALUES (?)', (str(idx), )).lastrowid
            self.cur.execute("INSERT INTO labels (track_id, label, email) VALUES (?, 'music', 'test')", (row, ))

        self.db.mark_recent_music(self.cur)

        new = self.cur.execute("SELECT COUNT(*) FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = 'recent')").fetchone()[0]
        old = self.cur.execute("SELECT COUNT(*) FROM tracks WHERE id NOT IN (SELECT track_id FROM labels WHERE label = 'recent')").fetchone()[0]

        self.assertEquals(200, new + old)
        self.assertEquals(100, new)


class PreshowMarker(TestCase):
    tables = ['tracks', 'labels', 'votes']

    def runTest(self):
        tracks = (
            (1, ('alice@example.com', )),
            (2, ('bob@example.com', )),
            (3, ('alice@example.com', 'bob@example.com', )),
        )

        for track in tracks:
            self.cur.execute('INSERT INTO tracks (id) VALUES (?)', (track[0], ))
            self.cur.execute("INSERT INTO labels (track_id, label, email) VALUES (?, 'music', 'test')", (track[0], ))
            for email in track[1]:
                self.cur.execute('INSERT INTO votes (track_id, vote, email) VALUES (?, 1, ?)', (track[0], email, ))

        self.db.mark_preshow_music(self.cur)

        rows = self.cur.execute("SELECT track_id FROM labels WHERE label = 'preshow-music'").fetchall()
        self.assertEquals(1, len(rows))
        self.assertEquals(3, rows[0][0])


class Stats(TestCase):
    tables = ['tracks']

    def runTest(self):
        for x in range(100):
            self.cur.execute('INSERT INTO tracks (length, weight) VALUES (?, ?)', (x, x, ))

        s = self.db.get_stats(self.cur)
        self.assertEquals(99, s['tracks'], 'zero weight track must NOT be in the stats')
        self.assertEquals(4950, s['seconds'])


class OrphansMarker(TestCase):
    tables = ['tracks', 'labels']

    def runTest(self):
        t1 = self.cur.execute('INSERT INTO tracks (title) VALUES (NULL)').lastrowid
        self.cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'music\', \'nobody\')', (t1, ))
        t2 = self.cur.execute('INSERT INTO tracks (title) VALUES (NULL)').lastrowid
        self.cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'foobar\', \'nobody\')', (t2, ))

        self.db.mark_orphans(cur=self.cur, quiet=True)

        rows = self.cur.execute('SELECT track_id FROM labels WHERE label = \'orphan\'').fetchall()
        self.assertEquals(1, len(rows), 'one track must have been labelled orphan')
        self.assertEquals(t2, rows[0][0], 'wrong track labelled orphan')
