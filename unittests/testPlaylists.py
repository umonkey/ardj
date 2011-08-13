import time
import unittest

from ardj.database import Open
from ardj.playlist import Playlist


class PlaylistTests(unittest.TestCase):
    def setUp(self):
        Playlist.reload("unittests/data/src/playlists.yaml")

    def test_parser(self):
        """Make sure special values are parsed."""
        data = Playlist.parse_file("- name: music\n  days: [1,5-7]\n  hours: [2,6-8]")
        self.assertEquals(data, [{"name": "music", "days": [1,5,6,7], "hours": [2,6,7,8], "labels": ["music"]}])

    def test_static_playlists(self):
        """Makes sure that the playlists.yaml file contains what we expect it
        to contain."""
        data = Playlist.get_all_static()
        self.assertEquals(data, [{"name": "music", "labels": ["music"]}])

    def test_automatic_reload(self):
        """Makes sure that playlists are reloaded when file timestamp
        changes."""
        self.assertEquals(Playlist.get_all_static(), [{"name": "music", "labels": ["music"]}])

        Playlist.static_data[0]["name"] = "cisum"
        self.assertEquals(Playlist.get_all_static(), [{"name": "cisum", "labels": ["music"]}])

        Playlist.static_time -= 1
        self.assertEquals(Playlist.get_all_static(), [{"name": "music", "labels": ["music"]}])

    def test_active_days(self):
        ts = time.mktime(time.strptime('2011-08-12 16:00', '%Y-%m-%d %H:%M'))  # this is a friday

        self.assertEquals(1, len(Playlist.get_all()), "wrong default playlists")

        Playlist.static_data[0]["days"] = [1]  # mondays only
        self.assertEquals(0, len(Playlist.get_active(ts)), "a playlist IS active while it MUST NOT be")

        Playlist.static_data[0]["days"] = [5]  # fridays only
        self.assertEquals(1, len(Playlist.get_active(ts)), "a playlist IS NOT active while it MUST be")

    def test_active_hours(self):
        ts = time.mktime(time.strptime('2011-08-12 16:00', '%Y-%m-%d %H:%M'))

        self.assertEquals(1, len(Playlist.get_all()), "wrong default playlists")

        Playlist.static_data[0]["hours"] = [15]
        self.assertEquals(0, len(Playlist.get_active(ts)), "a playlist IS active while it MUST NOT be")

        Playlist.static_data[0]["hours"] = [16]
        self.assertEquals(1, len(Playlist.get_active(ts)), "a playlist IS NOT active while it MUST be")

    def test_active_delay(self):
        ts = time.mktime(time.strptime('2011-08-12 16:00', '%Y-%m-%d %H:%M'))

        self.assertEquals(1, len(Playlist.get_all()), "wrong default playlists")

        pl = Playlist.get_all()[0]
        pl.set_last_played(ts)

        self.assertEquals(1, len(Playlist.get_active(ts)))

        Playlist.static_data[0]["delay"] = 10  # minutes
        self.assertEquals(0, len(Playlist.get_active(ts)), "the playlist MUST NOT be active")

        # 9:59 passed -- not ready
        self.assertEquals(0, len(Playlist.get_active(ts + 599)))

        # 10:00 passed -- ready
        self.assertEquals(1, len(Playlist.get_active(ts + 600)))

    def test_get_tracks(self):
        db = Open()
        ts = int(time.time())

        db.erase_tracks()

        db.add_track(artist="artist", title="track 1", labels=["music"])
        db.add_track(artist="artist", title="track 2", labels=["music"])
        db.add_track(artist="artist", title="track 3", labels=["cisum"])

        tracks = db.get_tracks(ts)
        self.assertEquals(3, len(tracks), "could not add all tracks")

        pl = Playlist.get_all()[0]

        tracks = pl.get_tracks(ts)
        self.assertEquals(2, len(tracks), "wrong number of returned tracks")
