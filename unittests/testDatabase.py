import os
import time
import unittest

import ardj.database


class DatabaseTests(unittest.TestCase):
    def test_something(self):
        db = ardj.database.Open()
        self.assertNotEquals(db, None)

    def test_get_tracks_to_scrobble(self):
        db = ardj.database.Open()
        db.get_tracks_to_scrobble()
        db.get_tracks_to_scrobble(["ye's", "n\"o", "maybe"])

    def test_get_tracks(self):
        db = ardj.database.Open()
        db.erase_tracks()

        ts = int(time.time())
        t1_id = db.add_track(artist="artist", title="track 1", weight=1.0, play_count=1, labels=["music"])
        t2_id = db.add_track(artist="artist", title="track 2", weight=1.5, play_count=2, labels=["music"])
        t3_id = db.add_track(artist="artist", title="track 3", weight=2.0, play_count=3, last_played=ts, labels=["cisum"])

        self.assertEquals(3, len(db.get_tracks(ts)))
        self.assertEquals(2, len(db.get_tracks(ts, labels=["music"])))
        self.assertEquals(1, len(db.get_tracks(ts, min_weight=1.7)))
        self.assertEquals(2, len(db.get_tracks(ts, max_weight=1.5)))
        self.assertEquals(1, len(db.get_tracks(ts, max_count=2)))

        self.assertEquals(2, len(db.get_tracks(ts, track_delay=60)))
        db.set_track_played(t2_id, ts)
        self.assertEquals(1, len(db.get_tracks(ts, track_delay=60)))

    def test_get_random_track(self):
        """Adds 3 random tracks then makes sure they're all picked during 20 tries."""
        db = ardj.database.Open()
        db.erase_tracks()

        ts = int(time.time())
        db.add_track(artist="artist", title="track 1", weight=1.0, play_count=1, labels=["music"])
        db.add_track(artist="artist", title="track 2", weight=1.5, play_count=2, labels=["music"])
        db.add_track(artist="artist", title="track 3", weight=2.0, play_count=3, last_played=ts, labels=["cisum"])

        ids = {}
        for x in range(20):
            track = db.get_random_track(ts)
            self.assertNotEquals(track, None)
            ids[track["id"]] = True
            if len(ids) == 3:
                break
        self.assertEquals(3, len(ids))

    def test_get_random_tracks_delay(self):
        """Adds 3 tracks then requests them by random using a delay.  All
        tracks must be found in 3 attempts."""
        db = ardj.database.Open()
        db.erase_tracks()

        ts = int(time.time())
        db.add_track(artist="artist", title="track 1", weight=1.0, play_count=1, labels=["music"])
        db.add_track(artist="artist", title="track 2", weight=1.5, play_count=2, labels=["music"])
        db.add_track(artist="artist", title="track 3", weight=2.0, play_count=3, labels=["cisum"])

        for attempts in range(10):
            ts += 120
            ids = {}
            for x in range(3):
                track = db.get_random_track(ts, touch=True, track_delay=1)
                self.assertNotEquals(track, None)
                ids[track["id"]] = True
            self.assertEquals(3, len(ids))
