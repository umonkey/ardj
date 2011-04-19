import imp
import os
import sys

import unittest

if __name__ == '__main__':
    names = sys.argv[1:] or [
        'unittests/tags.py',
    ]

    suite = unittest.TestSuite()

    for name in names:
        mod = imp.load_source('test_' + os.path.basename(name)[:-3], name)
        for member in getattr(mod, '__all__', dir(mod)):
            if type(getattr(mod, member)) == type:
                suite.addTest(getattr(mod, member)())

    print 'Logging to tests.log'
    sys.stdout = sys.stderr = open('tests.log', 'wb')

    unittest.TextTestRunner().run(suite)
