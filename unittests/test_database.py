import os
import unittest

import ardj.database as db
import ardj.tracks


class DatabaseTests(unittest.TestCase):
    tables = []

    def setUp(self):
        db.cli_init([])

    def tearDown(self):
        db.rollback()

    def test_filename(self):
        self.assertEquals('unittests/data/database.sqlite', db.Open().filename)

    def test_queue(self):
        db.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (0, 'test', ))
        self.assertEquals(1, db.fetchone('SELECT COUNT(*) FROM queue')[0], 'Failed to insert a record into queue.')

    def test_update(self):
        db.execute('DELETE FROM queue')
        row = db.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (1, 'ardj', ))
        self.assertEquals(row, 1)

        db.Open().update('queue', { 'owner': 'test', 'id': row })
        tmp = db.fetchone('SELECT * FROM queue')
        self.assertEquals(tmp, (1, 1, 'test'))

    def test_mark_recent(self):
        for idx in range(200):
            row = db.execute('INSERT INTO tracks (title) VALUES (?)', (str(idx), ))
            db.execute("INSERT INTO labels (track_id, label, email) VALUES (?, 'music', 'test')", (row, ))

        db.Open().mark_recent_music()

        new = db.fetchone("SELECT COUNT(*) FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = 'recent')")[0]
        old = db.fetchone("SELECT COUNT(*) FROM tracks WHERE id NOT IN (SELECT track_id FROM labels WHERE label = 'recent')")[0]

        self.assertEquals(200, new + old)
        self.assertEquals(100, new)

    def test_stats(self):  # FIXME
        """
        for x in range(100):
            db.execute('INSERT INTO tracks (length, weight) VALUES (?, ?)', (x, x, ))

        s = db.Open().get_stats()
        self.assertEquals(99, s['tracks'], 'zero weight track must NOT be in the stats')
        self.assertEquals(4950, s['seconds'])
        """

    def test_mark_orphans(self):
        t1 = db.execute('INSERT INTO tracks (title, weight) VALUES (NULL, 1)')
        db.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'music\', \'nobody\')', (t1, ))
        t2 = db.execute('INSERT INTO tracks (title, weight) VALUES (NULL, 1)')
        db.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'foobar\', \'nobody\')', (t2, ))

        if not db.Open().mark_orphans(quiet=True):
            self.fail('database.mark_orphans() failed to find tracks.')

        rows = db.fetch('SELECT track_id FROM labels WHERE label = \'orphan\'')
        self.assertEquals(1, len(rows), 'one track must have been labelled orphan, not %u' % len(rows))
        self.assertEquals(t2, rows[0][0], 'wrong track labelled orphan')

    def test_debug(self):
        sql = db.Open().debug('SELECT ?, ?', (1, 2, ), quiet=True)
        self.assertEquals('SELECT 1, 2', sql)

    def test_mark_liked_by(self):
        db.execute("DELETE FROM tracks")
        db.execute("DELETE FROM votes")
        db.execute("DELETE FROM labels")

        jids = ["a@example.com", "b@example.com", "c@example.com"]

        for idx in range(len(jids)):
            track_id = idx + 1
            db.execute("INSERT INTO tracks (id) VALUES (?)", (track_id, ))
            for jid in range(idx, len(jids)):
                db.execute("INSERT INTO votes (track_id, email, vote) VALUES (?, ?, ?)", (track_id, jids[jid], 1, ))

        count = ardj.tracks.add_label_to_tracks_liked_by("tmp", jids[1:], "test")
        self.assertEquals(2, count)

        rows = db.fetchcol("SELECT track_id FROM labels WHERE label = ?", ("tmp", ))
        self.assertEquals([1, 2], rows)
