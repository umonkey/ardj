import glob
import os
import sys

import unittest

from ardj import log


def run_all_tests():
    loader = unittest.defaultTestLoader
    loader.testMethodPrefix = "test_"
    suite = loader.discover(os.path.dirname(__file__))

    print('Logging to tests.log')
    sys.stdout = sys.stderr = open('tests.log', 'wb')
    log.install()

    runner = unittest.TextTestRunner().run(suite)
    if runner.errors or runner.failures:
        exit(1)


if __name__ == '__main__':
    run_all_tests()
