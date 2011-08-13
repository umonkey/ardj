import os
import unittest

import ardj.log

class Logging(unittest.TestCase):
    def DISABLED_runTest(self):
        ardj.log.info('hello, world!', quiet=True)
        self.assertTrue(os.path.exists('tests-ardj.log'))

        data = open('tests-ardj.log', 'rb').read()
        self.assertTrue('hello, world!' in data)
