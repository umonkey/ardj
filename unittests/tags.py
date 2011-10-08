import unittest

import ardj.tags


class FileNotFound(unittest.TestCase):
    def runTest(self):
        try:
            ardj.tags.raw('does/not/exist.mp3')
        except ardj.tags.FileNotFound:
            return
        self.fail('Missing file not reported.')


class UnsupportedFileType(unittest.TestCase):
    def runTest(self):
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
        self.assertEquals(self.classname, type(t).__name__)
        self.assertEquals(0, len(t.items()))

        t = ardj.tags.get(self.filename)
        self.assertEquals(3, t['length'])

        t['artist'] = 'somebody'
        t['title'] = 'something'
        t['ardj'] = 'ardj=1;yes=no;labels=one,two'
        ardj.tags.set(self.filename, t)

        t2 = ardj.tags.get(self.filename)
        self.assertEquals(3, t2['length'])
        self.assertEquals('somebody', t2['artist'])
        self.assertEquals('something', t2['title'])
        self.assertEquals('no', t2['yes'])
        self.assertEquals(['one', 'two'], t2['labels'])


class MP3(OGG):
    filename = 'unittests/data/silence.mp3'
    classname = 'EasyID3'
