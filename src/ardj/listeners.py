# vim: set fileencoding=utf-8:

import csv
import logging
import os
import re
import sys
import time

import ardj.settings
import ardj.util


def get_count():
    """Returns the number of active listeners."""
    url = ardj.settings.get("icecast_status_url")
    if not url:
        logging.debug('Unable to count listeners: icecast/stats/url not set.')
        return 0

    data = ardj.util.fetch(url, quiet=True, ret=True)
    if data is None:
        logging.error("Could not fetch listener count.")
        return 0

    csv = re.findall(r"<pre>(.*)</pre>", data, re.M | re.S)
    lines = csv[0].strip().split("\n")
    for line in lines:
        cells = line.split(",")
        if cells[0] == "Global":
            return int(cells[3])

    return lines


def format_data(sql, params, converters, header=None):
    data = ardj.database.fetch(sql, params)
    f = csv.writer(sys.stdout)
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


def cmd_now():
    """Print current listener count."""
    print get_count()


def cli_total():
    """Prints overall statistics."""
    sql = 'SELECT max(l.ts), t.artist, t.title, SUM(l.listeners) AS count, t.id, t.weight FROM tracks t INNER JOIN playlog l ON l.track_id = t.id WHERE weight > 0 GROUP BY t.artist, t.title ORDER BY artist COLLATE UNICODE, title COLLATE UNICODE'
    params = []
    format_data(sql, params, [
        lambda d: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d)),
        lambda x: unicode(x).encode('utf-8'),
        lambda x: unicode(x).encode('utf-8'),
        str,
        str,
        lambda w: '%.02f' % w,
    ], ['last_played', 'artist', 'title', 'listeners', 'track_id', 'weight'])


def cli_yesterday():
    """Prints yesterday's statistics."""
    sql = 'SELECT l.ts, t.id, t.artist, t.title, l.listeners FROM tracks t INNER JOIN playlog l ON l.track_id = t.id WHERE l.ts BETWEEN ? AND ? AND weight > 0 ORDER BY l.ts'
    params = get_yesterday_ts()
    format_data(sql, params, [
        lambda d: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(d)),
        str,
        lambda x: unicode(x).encode('utf-8'),
        lambda x: unicode(x).encode('utf-8'),
        str,
    ], ['time', 'track_id', 'artist', 'title', 'listeners'])
