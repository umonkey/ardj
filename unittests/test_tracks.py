import logging
import unittest

from ardj import database
from ardj import tracks

class TrackSelectionTests(unittest.TestCase):
    def setUp(self):
        database.cli_init()

    def tearDown(self):
        database.execute("DELETE FROM tracks")
        database.execute("DELETE FROM labels")

    def test_sticky_labels(self):
        genres = ["rock", "jazz", "calm"]
        for genre in genres:
            for idx in range(10):
                track_id = database.execute("INSERT INTO tracks (weight, artist, filename) VALUES (1, 'somebody', 'dummy.mp3')")
                database.execute("INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)", (track_id, "music", "-", ))
                database.execute("INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)", (track_id, genre, "-", ))
                logging.debug("track %u genre: %s" % (track_id, genre))

        logging.debug(database.fetch("SELECT * FROM labels"))

        playlist = {
            "name": "sticky",
            "labels": ["music"],
            "sticky_labels": genres,
        }

        sticky_label, track = self._pick_track(playlist, genres)
        logging.debug("Picked first track %u with labels: %s, sticky=%s" % (track["id"], track.get_labels(), sticky_label))

        # Make sure 100 tracks follow this rule.
        for idx in range(100):
            new_label, track = self._pick_track(playlist, genres)
            self.assertEquals(new_label, sticky_label)

        # TODO: make sure the sticky label is reset when changing playlists.

    def _pick_track(self, playlist, genres):
        track_id = tracks.get_random_track_id_from_playlist(playlist, None)
        if track_id is None:
            self.fail("Could not pick a random track.")
        track = tracks.Track.get_by_id(track_id)
        track_labels = track.get_labels()

        sticky_label = set(track_labels) & set(genres)
        if not sticky_label:
            self.fail("Track has no sticky label.")
        sticky_label = list(sticky_label)[0]

        return sticky_label, track
