# vim: set fileencoding=utf-8:

import glob
import gzip
import os
import sys
import time

from sqlite3 import dbapi2 as sqlite

import ardj.log
import ardj.settings

USAGE = """Usage: ardj icelog command

Commands:
    show-agents     -- print statistics
    add             -- add new files to the database
"""

def parse_log_line(line):
    # 127.0.0.1 - - [30/Jan/2011:07:45:13 +0300] "GET /admin/stats.xml HTTP/1.1" 200 1523 "-" "collectd/4.8.2" 1
    remote_addr, date, uri, status, length, duration, agent = (None,) * 7
    try:
        parts = line.strip().split(' ')
        remote_addr = parts[0]
        date = time.strftime('%Y-%m-%d %H:%M:%S', time.strptime(parts[3][1:], '%d/%b/%Y:%H:%M:%S'))
        #date = time.strptime(parts[3][1:], '%d/%b/%Y:%H:%M:%S')
        uri = parts[6]
        status = parts[8]
        length = parts[9]
        duration = parts[-1]
        agent = u' '.join(parts[11:-2]).lstrip('"')
    except Exception, e:
        ardj.log.error('Unable to parse log line: %s; %s' % (e, line))
    return date, remote_addr, uri or '', status, length, duration, agent

def add_files(filenames, dbname):
    db = sqlite.connect(dbname)
    cur = db.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS log (date TEXT, remote_addr TEXT, uri TEXT, seconds INTEGER, bytes INTEGER)')

    for filename in filenames:
        f = gzip.open(filename, 'rb')
        while True:
            line = f.readline(16384)
            if line == '':
                break
            date, remote_addr, uri, status, length, duration, agent = parse_log_line(line)
            if uri.endswith('.mp3') and status == '200' and duration:
                cur.execute('INSERT INTO log VALUES (?, ?, ?, ?, ?, ?)', (date, remote_addr, uri, duration, length, agent, ))
        try:
            os.unlink(filename)
            db.commit()
        except Exception, e:
            ardj.log.error('Could not remove file %s: %s' % (filename, e))
            db.rollback()

def show_agent_stats(dbname):
    """Shows overall user-agent statistics."""
    db = sqlite.connect(dbname)
    cur = db.cursor()

    result = {}
    for row in cur.execute('SELECT agent FROM log WHERE agent IS NOT NULL').fetchall():
        if row[0]:
            agent = row[0].split(' ')[0]
            agent = agent.split('/')[0]
            if agent not in result:
                result[agent] = 0
            result[agent] += 1

    total = float(sum(result.values()))

    for row in sorted([(x, result[x]) for x in result], key=lambda r: r[1], reverse=True):
        print '%s: %.2f%%' % (row[0], float(row[1]) / total * 100.0)


def run_cli(args):
    """Implements the "ardj icelog" command."""
    dbname = ardj.settings.getpath('icecast/access_log_db', fail=True)
    if not os.path.exists(dbname):
        raise Exception('Icecast logs db %s does not exist.' % dbname)
    if len(args) and args[0] == 'show-agents':
        return show_agent_stats(dbname)
    if len(args) and args[0] == 'add':
        return add_files(glob.glob(ardj.settings.get('icecast/access_log_files', '/var/log/icecast2/access.log.*.gz')), dbname)
    print USAGE
