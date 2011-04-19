import StringIO
import unittest

import ardj.database
import ardj.listeners
import ardj.tracks


class Count(unittest.TestCase):
    def runTest(self):
        count = ardj.listeners.get_count()
        self.assertEquals(int, type(count))


class FormatData(unittest.TestCase):
    def runTest(self):
        data = [
            [ 1, 'two', 3, ],
            [ 1, 'two', 3, ],
        ]

        converters = [
            str,
            str,
            lambda x: str(x + 1),
        ]

        output = StringIO.StringIO()
        ardj.listeners.format_data(data, converters, output)

        self.assertEquals('1,two,4\r\n1,two,4\r\n', output.getvalue())


class Totals(unittest.TestCase):
    def runTest(self):
        db = ardj.database.Open()
        cur = ardj.database.cursor()

        self.assertEquals(0, cur.execute('SELECT COUNT(*) FROM tracks').fetchone()[0])

        t1 = cur.execute('INSERT INTO tracks (artist, title) VALUES (?, ?)', ('nobody.one', 'Duck', )).lastrowid
        t2 = cur.execute('INSERT INTO tracks (artist, title) VALUES (?, ?)', ('mindthings', 'Emotion Vibes', )).lastrowid

        ardj.tracks.log(t1, listener_count=3, ts=1, cur=cur)
        ardj.tracks.log(t1, listener_count=1, ts=2, cur=cur)
        ardj.tracks.log(t2, listener_count=1, ts=9, cur=cur)

        output = StringIO.StringIO()
        ardj.listeners.show_total(cur=cur, output=output)
        self.assertEquals('mindthings,Emotion Vibes,1\r\nnobody.one,Duck,4\r\n', output.getvalue())

        output = StringIO.StringIO()
        ardj.listeners.show_recent(cur=cur, output=output)
        self.assertEquals('1970-01-01 03:00:09,2,mindthings,Emotion Vibes,1\r\n1970-01-01 03:00:02,1,nobody.one,Duck,1\r\n1970-01-01 03:00:01,1,nobody.one,Duck,3\r\n', output.getvalue())

        output = StringIO.StringIO()
        ardj.listeners.show_recent(1, cur=cur, output=output)
        self.assertEquals('1970-01-01 03:00:09,2,mindthings,Emotion Vibes,1\r\n', output.getvalue())

        db.rollback()
