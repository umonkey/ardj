# vim: set fileencoding=utf-8:

import csv
import glob
import gzip
import os
import sys

USAGE = """Usage: ardj listeners print|update"""

def merge(filenames):
    """Reads specified files, merges track listener counts."""
    data = {}
    for filename in filenames:
        if filename.endswith('.gz'):
            f = gzip.open(filename, 'rb')
        else:
            f = open(filename, 'rb')
        r = csv.reader(f)
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

def format_data(data, out):
    f = csv.writer(out)
    for artist in sorted(data.keys()):
        tracks = data[artist]
        for title in sorted(tracks.keys()):
            f.writerow([artist.encode('utf-8'), title.encode('utf-8'), tracks[title]])

def run_cli(args):
    """Implements the "ardj listeners" command."""
    if len(args) and args[0] == 'print':
        output = sys.stdout
    elif len(args) and args[0] == 'update':
        output = open('/radio/data/totals.csv', 'wb')
    else:
        print USAGE
        return

    filenames = glob.glob('/radio/data/listeners.csv-*.gz')
    if not filenames:
        print 'No files to merge.'
        return
    format_data(merge(filenames), out)
