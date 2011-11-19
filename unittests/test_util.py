import os
import unittest2 as unittest

import ardj.util


class Run(unittest.TestCase):
    def test_run(self):
        self.assertTrue(ardj.util.run(['make'], quiet=True))
        self.assertFalse(ardj.util.run(['make', 'no-such-target'], quiet=True))

    def test_mktemp(self):
        f = ardj.util.mktemp(suffix='.txt')
        self.assertTrue(os.path.exists(str(f)))
        self.assertTrue(str(f).endswith('.txt'))

    def test_temp_file_delete(self):
        f = ardj.util.mktemp(suffix='.txt')
        self.assertTrue(os.path.exists(str(f)))
        fn = str(f)
        f = None
        del f
        self.assertFalse(os.path.exists(str(fn)))

    def test_copy_file(self):
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

    def test_move_file(self):
        tmp = ardj.util.mktemp()
        dst = 'temp.file'
        self.assertFalse(os.path.exists(dst))
        self.assertTrue(ardj.util.move_file(str(tmp), dst))
        self.assertFalse(os.path.exists(str(tmp)))
        self.assertTrue(os.path.exists(dst))
        os.unlink(dst)
        self.assertFalse(os.path.exists(dst))

    def test_format_duration(self):
        self.assertEquals('00', ardj.util.format_duration(0))
        self.assertEquals('1:00', ardj.util.format_duration(60))
        self.assertEquals('1:00:00', ardj.util.format_duration(3600))

        self.assertEquals('18:54 ago', ardj.util.format_duration(100, now=1234, age=True))

    def test_md5(self):
        self.assertEquals('3e6b69a3175e035b37e02ef35fc73e65', ardj.util.filemd5('unittests/data/src/silence.mp3'))

    def test_find_exe(self):
        self.assertTrue(ardj.util.is_command("python"))
        self.assertFalse(ardj.util.is_command("this should never exist"))
