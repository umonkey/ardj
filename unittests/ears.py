import StringIO
import unittest

import ardj.ears


class Format(unittest.TestCase):
    def runTest(self):
        data = {
            'one': { 'song': 1 },
            'two': { 'song': 2 },
        }

        out = StringIO.StringIO()
        ardj.ears.format_data(data, out)

        self.assertEquals('one,song,1\r\ntwo,song,2\r\n', out.getvalue())
