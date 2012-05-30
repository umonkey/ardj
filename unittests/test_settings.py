import os
import unittest

import ardj.settings


class Settings(unittest.TestCase):
    def test_get(self):
        s = ardj.settings.load()
        self.assertEquals('unittests/data/settings.yaml', s.filename)

        self.assertEquals('unittests/data/database.sqlite', ardj.settings.get('database/local'))
        self.assertEquals(os.path.expanduser('~'), ardj.settings.getpath('database/local/missing', '~'))

        try:
            ardj.settings.get('database/local/error', fail=True)
            self.fail('ardj.settings.get(k, fail=True) failed to raise KeyError.')
        except KeyError:
            pass

    def test_load_instance(self):
        a = ardj.settings.load()
        b = ardj.settings.load()
        self.assertEquals(id(a), id(b))

    def test_musicdir(self):
        a = ardj.settings.get_music_dir()
        b = os.path.realpath('unittests/data')
        self.assertEquals(a, b)

    def test_playlists(self):
        a = ardj.settings.load().get_playlists()
        self.assertEquals(type(a), list)
        self.assertEquals(1, len(a))
