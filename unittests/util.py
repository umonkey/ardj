import os
import unittest

import ardj.util


class Run(unittest.TestCase):
    def runTest(self):
        self.assertTrue(ardj.util.run(['make'], quiet=True))
        self.assertFalse(ardj.util.run(['make', 'no-such-target'], quiet=True))


class TempFile(unittest.TestCase):
    def runTest(self):
        f = ardj.util.mktemp(suffix='.txt')
        self.assertTrue(os.path.exists(str(f)))
        self.assertTrue(str(f).endswith('.txt'))


class TempFileDelete(unittest.TestCase):
    def runTest(self):
        f = ardj.util.mktemp(suffix='.txt')
        self.assertTrue(os.path.exists(str(f)))
        fn = str(f)
        f = None
        del f
        self.assertFalse(os.path.exists(str(fn)))


class Fetch(unittest.TestCase):
    def runTest(self):
        tmp = ardj.util.fetch('http://www.tmradio.net/favicon.ico')
        self.assertTrue(str(tmp).endswith('.ico'))


class Upload(unittest.TestCase):
    def runTest(self):
        pass # TODO: find a way to test this


class UploadMusic(unittest.TestCase):
    def runTest(self):
        pass # TODO: find a way to test this


class CopyFile(unittest.TestCase):
    def runTest(self):
        tmp = ardj.util.mktemp()
        dst = 'temp.file'
        if os.path.exists(dst):
            os.unlink(dst)
        self.assertFalse(os.path.exists(dst))
        self.assertTrue(ardj.util.copy_file(str(tmp), dst))
        self.assertTrue(os.path.exists(str(tmp)))
        self.assertTrue(os.path.exists(dst))
        os.unlink(dst)
        self.assertFalse(os.path.exists(dst))


class MoveFile(unittest.TestCase):
    def runTest(self):
        tmp = ardj.util.mktemp()
        dst = 'temp.file'
        self.assertFalse(os.path.exists(dst))
        self.assertTrue(ardj.util.move_file(str(tmp), dst))
        self.assertFalse(os.path.exists(str(tmp)))
        self.assertTrue(os.path.exists(dst))
        os.unlink(dst)
        self.assertFalse(os.path.exists(dst))


class FormatDuration(unittest.TestCase):
    def runTest(self):
        self.assertEquals('00', ardj.util.format_duration(0))
        self.assertEquals('1:00', ardj.util.format_duration(60))
        self.assertEquals('1:00:00', ardj.util.format_duration(3600))

        self.assertEquals('18:54 ago', ardj.util.format_duration(100, now=1234, age=True))


class MD5(unittest.TestCase):
    def runTest(self):
        self.assertEquals('3e6b69a3175e035b37e02ef35fc73e65', ardj.util.filemd5('unittests/data/src/silence.mp3'))
