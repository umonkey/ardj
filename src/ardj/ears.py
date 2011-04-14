# vim: set fileencoding=utf-8:

"""Aggregates play counts.

Reads files specified at the command line, sums listeners, prints results in
CSV to stdout.  Files are of the form:

artist,title,listeners

This command is designed for use with the logrotate daemon.
"""

import csv
import os
import sys

import ardj.log
import ardj.settings

def merge(filenames):
    data = {}
    for filename in filenames:
        if not os.path.exists(filename):
            ardj.log.info('WARNING: file %s not found.' % filename)
            continue
        r = csv.reader(open(filename, 'rb'))
        for row in r:
            if len(row) < 4:
                continue
            artist = row[2].strip().decode('utf-8')
            title = row[3].strip().decode('utf-8')
            count = int(row[4])
            if artist not in data:
                data[artist] = {}
            if title not in data[artist]:
                data[artist][title] = 0
            data[artist][title] += count
    return data

def format_data(data):
    f = csv.writer(sys.stdout)
    for artist in sorted(data.keys()):
        tracks = data[artist]
        for title in sorted(tracks.keys()):
            f.writerow([artist.encode('utf-8'), title.encode('utf-8'), tracks[title]])

def aggregate(args):
    """Aggregates play counts."""
    format_data(merge(args))
