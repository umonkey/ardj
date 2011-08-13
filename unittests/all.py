import imp
import os
import sys

import unittest

sys.path.insert(0, "src")
sys.path.insert(0, "unittest")


def run_tests():
    loader = unittest.defaultTestLoader
    loader.testMethodPrefix = 'test_'

    print 'Logging to tests.log'
    sys.stderr = sys.stdout = open('tests.log', 'wb')

    if len(sys.argv) > 1:
        for name in sys.argv[1:]:
            info = imp.find_module(name)
            module = imp.load_module(name, *info)

            suite = loader.loadTestsFromModule(module)
            unittest.TextTestRunner().run(suite)
    else:
        # run all tests
        current_dir = os.path.dirname(os.path.realpath(__file__))
        suite = loader.discover(current_dir)
        unittest.TextTestRunner().run(suite)


if __name__ == '__main__':
    run_tests()
