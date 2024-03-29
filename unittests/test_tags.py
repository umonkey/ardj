import unittest

import ardj.tags


class FileNotFound(unittest.TestCase):
    def test_not_found(self):
        try:
            ardj.tags.raw('does/not/exist.mp3')
        except ardj.tags.FileNotFound:
            return
        self.fail('Missing file not reported.')

    def test_unsupported_file(self):
        try:
            ardj.tags.raw(__file__)
        except ardj.tags.UnsupportedFileType:
            return
        self.fail('Unexpected file was opened OK.')


class OGG(unittest.TestCase):
    filename = 'unittests/data/silence.ogg'
    classname = 'OggVorbis'

    def runTest(self):
        t = ardj.tags.raw(self.filename)
        self.assertEqual(self.classname, type(t).__name__)
        self.assertEqual(0, len(list(t.items())))

        t = ardj.tags.get(self.filename)
        self.assertEqual(3, t['length'])

        t['artist'] = 'somebody'
        t['title'] = 'something'
        t['labels'] = ["one", "two"]
        ardj.tags.set(self.filename, t)

        t2 = ardj.tags.get(self.filename)
        self.assertEqual(3, t2['length'])
        self.assertEqual('somebody', t2['artist'])
        self.assertEqual('something', t2['title'])
        self.assertEqual(['one', 'two'], t2['labels'])


class MP3(OGG):
    filename = 'unittests/data/silence.mp3'
    classname = 'EasyID3'
