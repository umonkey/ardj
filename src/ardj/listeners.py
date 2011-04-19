# vim: set fileencoding=utf-8:

import csv
import os
import re
import sys
import time

import ardj.settings
import ardj.util


USAGE = """Usage: ardj listeners command...

Commands:
  show recent    -- show what's been listened to recently
  show total     -- show aggregate track counts
"""


def get_count():
    """Returns the number of active listeners."""
    url = ardj.settings.get('icecast/stats/url')
    if not url:
        ardj.log.debug('Unable to count listeners: icecast/stats/url not set.')
        return 0

    data = ardj.util.fetch(url, user=ardj.settings.get('icecast/stats/login'), password=ardj.settings.get('icecast/stats/password'), quiet=True, ret=True)

    stats_re = re.compile(ardj.settings.get('icecast_stats/re', '<listeners>(\d+)</listeners>'))
    m = stats_re.search(data)
    if not m:
        ardj.log.warning('Could not find listener count in icecast2 stats.xml')
        return 0

    return int(m.group(1))


def format_data(data, converters, output=None):
    f = csv.writer(output or sys.stdout)
    for row in data:
        row = [converters[x](row[x]) for x in range(len(row))]
        f.writerow(row)



def show_total(cur=None, output=None):
    """Returns total playcounts."""
    cur = cur or ardj.database.cursor()
    cur.execute('SELECT t.artist, t.title, SUM(l.listeners) AS count FROM tracks t INNER JOIN playlog l ON l.track_id = t.id GROUP BY t.artist, t.title ORDER BY artist, title')
    format_data(cur.fetchall(), [
        lambda x: unicode(x).encode('utf-8'),
        lambda x: unicode(x).encode('utf-8'),
        str,
    ], output=output)


def show_recent(limit=1000, cur=None, output=None):
    """Returns last X player tracks."""
    cur = cur or ardj.database.cursor()
    sql = 'SELECT l.ts, t.id, t.artist, t.title, l.listeners FROM tracks t INNER JOIN playlog l ON l.track_id = t.id ORDER BY l.ts DESC LIMIT ' + str(limit)
    cur.execute(sql)
    format_data(cur.fetchall(), [
        lambda d: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d)),
        str,
        lambda x: unicode(x).encode('utf-8'),
        lambda x: unicode(x).encode('utf-8'),
        str,
    ], output=output)


def run_cli(args):
    """Implements the "ardj listeners" command."""
    if len(args) >= 2 and args[0] == 'show':
        if args[1] == 'total':
            fn = show_total
        elif args[1] == 'recent':
            fn = show_recent
        return fn()

    print USAGE
    return 1
