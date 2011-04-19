import unittest

import ardj.database
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
