import glob
import imp
import os
import sys

import unittest

if __name__ == '__main__':
    names = sys.argv[1:] or glob.glob('unittests/*.py')

    total = [os.path.basename(f) for f in glob.glob(os.path.join('src', 'ardj', '*.py'))]
    tested = [os.path.basename(f) for f in names]
    not_tested = [f for f in total if f not in tested]

    if len(not_tested):
        print 'These files are not tested: src/ardj/' + ", src/ardj/".join(sorted(not_tested)) + "."

    suite = unittest.TestSuite()

    for name in names:
        mod = imp.load_source('test_' + os.path.basename(name)[:-3], name)
        for member in getattr(mod, '__all__', dir(mod)):
            if type(getattr(mod, member)) == type:
                suite.addTest(getattr(mod, member)())

    print 'Logging to tests.log'
    sys.stdout = sys.stderr = open('tests.log', 'wb')

    unittest.TextTestRunner().run(suite)
