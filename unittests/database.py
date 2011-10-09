import os
import unittest

import ardj.database


class TestCase(unittest.TestCase):
    tables = []

    def __init__(self):
        unittest.TestCase.__init__(self)

    def runTest(self):
        pass

    def setUp(self):
        ardj.database.cli_init([])

        for table in self.tables:
            self.check_table_size(table)

    def tearDown(self):
        ardj.database.rollback()

        for table in self.tables:
            self.check_table_size(table)

    def check_table_size(self, name, wanted=0):
        size = ardj.database.fetchone('SELECT COUNT(*) FROM ' + name)[0]
        self.assertEquals(wanted, size, 'table %s has %u records instead of %u.' % (name, size, wanted))


class Open(TestCase):
    def runTest(self):
        self.assertEquals('unittests/data/database.sqlite', ardj.database.Open().filename)


class Transactions(TestCase):
    tables = ['queue']

    def runTest(self):
        ardj.database.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (0, 'test', ))
        self.assertEquals(1, ardj.database.fetchone('SELECT COUNT(*) FROM queue')[0], 'Failed to insert a record into queue.')


class Update(TestCase):
    def runTest(self):
        ardj.database.execute('DELETE FROM queue')
        row = ardj.database.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (1, 'ardj', ))
        self.assertEquals(row, 1)

        ardj.database.Open().update('queue', { 'owner': 'test', 'id': row })
        tmp = ardj.database.fetchone('SELECT * FROM queue')
        self.assertEquals(tmp, (1, 1, 'test'))


class Debug(TestCase):
    def runTest(self):
        sql = ardj.database.Open().debug('SELECT ?, ?', (1, 2, ), quiet=True)
        self.assertEquals('SELECT 1, 2', sql)


class RecentMarker(TestCase):
    tables = ['tracks', 'labels']

    def runTest(self):
        for idx in range(200):
            row = ardj.database.execute('INSERT INTO tracks (title) VALUES (?)', (str(idx), ))
            ardj.database.execute("INSERT INTO labels (track_id, label, email) VALUES (?, 'music', 'test')", (row, ))

        ardj.database.Open().mark_recent_music()

        new = ardj.database.fetchone("SELECT COUNT(*) FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = 'recent')")[0]
        old = ardj.database.fetchone("SELECT COUNT(*) FROM tracks WHERE id NOT IN (SELECT track_id FROM labels WHERE label = 'recent')")[0]

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
            ardj.database.execute('INSERT INTO tracks (id) VALUES (?)', (track[0], ))
            ardj.database.execute("INSERT INTO labels (track_id, label, email) VALUES (?, 'music', 'test')", (track[0], ))
            for email in track[1]:
                ardj.database.execute('INSERT INTO votes (track_id, vote, email) VALUES (?, 1, ?)', (track[0], email, ))

        ardj.database.Open().mark_preshow_music()

        rows = ardj.database.fetch("SELECT track_id FROM labels WHERE label = 'preshow-music'")
        self.assertEquals(1, len(rows))
        self.assertEquals(3, rows[0][0])


class Stats(TestCase):
    tables = ['tracks']

    def fixme_runTest(self):
        for x in range(100):
            ardj.database.execute('INSERT INTO tracks (length, weight) VALUES (?, ?)', (x, x, ))

        s = ardj.database.Open().get_stats()
        self.assertEquals(99, s['tracks'], 'zero weight track must NOT be in the stats')
        self.assertEquals(4950, s['seconds'])


class OrphansMarker(TestCase):
    tables = ['tracks', 'labels']

    def runTest(self):
        t1 = ardj.database.execute('INSERT INTO tracks (title, weight) VALUES (NULL, 1)')
        ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'music\', \'nobody\')', (t1, ))
        t2 = ardj.database.execute('INSERT INTO tracks (title, weight) VALUES (NULL, 1)')
        ardj.database.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'foobar\', \'nobody\')', (t2, ))

        if not ardj.database.Open().mark_orphans(quiet=True):
            self.fail('database.mark_orphans() failed to find tracks.')

        rows = ardj.database.fetch('SELECT track_id FROM labels WHERE label = \'orphan\'')
        self.assertEquals(1, len(rows), 'one track must have been labelled orphan, not %u' % len(rows))
        self.assertEquals(t2, rows[0][0], 'wrong track labelled orphan')
