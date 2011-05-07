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
  stats -- update totals.csv and yesterday.csv
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


def format_data(sql, params, converters, setting, header=None):
    filename = ardj.settings.getpath(setting)
    if filename:
        print 'Writing to %s' % filename
        data = ardj.database.cursor().execute(sql, params).fetchall()
        f = csv.writer(open(filename, 'w'))
        if header:
            f.writerow(header)
        for row in data:
            row = [converters[x](row[x]) for x in range(len(row))]
            f.writerow(row)


def get_yesterday_ts():
    """Returns timestamps for yesterday and today midights, according to local
    time zone."""
    now = int(time.time())
    diff = time.daylight and time.altzone or time.timezone
    today = now - (now % 86400) + diff
    if diff < 0:
        today += 86400
    yesterday = today - 86400
    return yesterday, today


def dump_statistics():
    """Saves both kinds of statistics to configured files (total.csv and
    yesterday.csv by default)."""
    sql = 'SELECT max(l.ts), t.artist, t.title, SUM(l.listeners) AS count, t.id, t.weight FROM tracks t INNER JOIN playlog l ON l.track_id = t.id WHERE weight > 0 GROUP BY t.artist, t.title ORDER BY artist COLLATE UNICODE, title COLLATE UNICODE'
    params = []
    format_data(sql, params, [
        lambda d: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d)),
        lambda x: unicode(x).encode('utf-8'),
        lambda x: unicode(x).encode('utf-8'),
        str,
        str,
        lambda w: '%.02f' % w,
    ], 'statistics/listeners/total_csv', [ 'last_played', 'artist', 'title', 'listeners', 'id', 'weight' ])

    sql = 'SELECT l.ts, t.id, t.artist, t.title, l.listeners FROM tracks t INNER JOIN playlog l ON l.track_id = t.id WHERE l.ts BETWEEN ? AND ? AND weight > 0 ORDER BY l.ts'
    params = get_yesterday_ts()
    format_data(sql, params, [
        lambda d: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d)),
        str,
        lambda x: unicode(x).encode('utf-8'),
        lambda x: unicode(x).encode('utf-8'),
        str,
    ], 'statistics/listeners/yesterday_csv')


def run_cli(args):
    """Implements the "ardj listeners" command."""
    command = ''.join(args[:1])

    if command == 'stats':
        return dump_statistics()

    print USAGE
    return 1
