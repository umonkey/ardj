import time
import unittest

import ardj.database
import ardj.log
import ardj.tracks
import ardj.shitlist


class ShitList(unittest.TestCase):
    def runTest(self):
        db = ardj.database.Open()
        cur = db.cursor()

        for x in range(0, 20, 1):
            weight = float(x) / 20
            track_id = cur.execute('INSERT INTO tracks (weight) VALUES (?)', (weight, )).lastrowid
            cur.execute('INSERT INTO labels (track_id, label, email) VALUES (?, \'music\', \'ardj\')', (track_id, ))

        self.assertEquals(0.5, ardj.shitlist.get_highest_weight(cur))
        self.assertEquals(10, len(ardj.shitlist.pick_tracks(cur)))

        ardj.shitlist.queue_tracks(cur=cur)
        queue = ardj.tracks.get_queue(cur)
        self.assertTrue(len(queue) >= 10)

        db.rollback()


class Purge(unittest.TestCase):
    def runTest(self):
        db = ardj.database.Open()
        cur = db.cursor()

        try:
            nz = lambda t, c=0: self.assertEquals(c, cur.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0])
            nz('tracks')
            nz('votes')

            now = time.time()
            for x in range(20):
                ts = int(now - x * 86400)
                track_id = cur.execute('INSERT INTO tracks (filename, weight) VALUES (\'test.mp3\', 0.1)').lastrowid
                ardj.log.debug('Added track id=%2u ts=%s' % (track_id, ts))
                cur.execute('INSERT INTO votes (track_id, vote, email, ts) VALUES (?, 0, \'test\', ?)', (track_id, ts, ))

            nz('tracks', 20)
            nz('votes', 20)

            ardj.shitlist.purge_old_tracks(cur=cur)
            self.assertEquals(15, cur.execute('SELECT COUNT(*) FROM tracks WHERE weight > 0').fetchone()[0])
        finally:
            db.rollback()
