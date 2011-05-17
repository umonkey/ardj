# vim: set fileencoding=utf-8:

import mutagen
import email.utils
import os
import sys
import time

import ardj.log
import ardj.settings
import ardj.twitter

USAGE = """Usage: ardj stream start|stop"""

MAX_FILE_AGE_DAYS = 7

RSS_CHANNEL = u'''<?xml version="1.0"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<atom:link href="http://files.tmradio.net/live-dump/live.xml" rel="self" type="application/rss+xml"/>
<language>ru-RU</language>
<docs>http://blogs.law.harvard.edu/tech/rss</docs>
<generator>ardj</generator>
<title>Тоже мне радио: прямые эфиры</title>
<description>Все прямые эфиры tmradio</description>
<link>http://www.tmradio.net/mcast.html</link>
<pubDate>Thu, 03 Mar 2011 22:12:22 -0000</pubDate>
<lastBuildDate>Thu, 03 Mar 2011 22:12:22 -0000</lastBuildDate>
###ITEMS###</channel>
</rss>
'''

RSS_ITEM = u'''<item>
<title>Прямой эфир от %(date)s (%(duration)u мин.)</title>
<description>Запись произведена роботом и не обработана.</description>
<pubDate>%(rss_date)s</pubDate>
<guid>%(link)s</guid>
<enclosure url="%(link)s" type="audio/mpeg" length="%(length)u"/>
<author>info@tmradio.net (ardj)</author>
</item>
'''

def get_fqfn(filename):
    if os.path.dirname(filename) == '':
        dirname = os.path.dirname(ardj.settings.getpath('stream/dump', fail=True))
        filename = os.path.join(dirname, filename)
    return filename

def get_air_time(filename):
    return time.strptime(get_fqfn(filename), ardj.settings.getpath('stream/dump_rename_to', fail=True))

def get_air_duration(filename):
    tags = mutagen.File(filename)
    return int(tags.info.length / 60)

def purge(dirname):
    limit = time.time() - MAX_FILE_AGE_DAYS * 86400
    for filename in os.listdir(dirname):
        filename = os.path.join(dirname, filename)
        ctime = os.stat(filename).st_ctime
        if ctime < limit:
            ardj.log.info('Delete file: %s' % filename)
            os.unlink(filename)

def twit_file(filename, silent=False):
    dur = get_air_duration(filename)
    if dur < ardj.settings.get('stream/twit_duration_min', 10):
        return
    date = get_air_time(filename)
    twit = time.strftime(ardj.settings.get('stream/twit_end').encode('utf-8')).decode('utf-8')
    twit = twit.replace('URL', ardj.settings.get('stream/base_url') + os.path.basename(filename))
    twit = twit.replace('LENGTH', str(dur))

    if not silent:
        ardj.twitter.send_message(twit)

def update_rss(dirname):
    xml = u''
    for filename in sorted(os.listdir(dirname)):
        filename = os.path.join(dirname, filename)
        date = get_air_time(filename)
        dur = get_air_duration(filename)
        xml += RSS_ITEM % {
            'date': time.strftime('%d.%m.%Y, %H:%M', date),
            'duration': get_air_duration(filename),
            'link': ardj.settings.get('stream/base_url', '') + filename,
            'length': os.stat(filename).st_size,
            'rss_date': email.utils.formatdate(time.mktime(date)),
        }

    xml = RSS_CHANNEL.replace('###ITEMS###', xml)
    open(ardj.settings.getpath('stream/rss_name'), 'wb').write(xml.encode('utf-8'))


def start_stream():
    src = ardj.settings.getpath('stream/dump', fail=True)
    dst = time.strftime(ardj.settings.getpath('stream/dump_rename_to', fail=True))

    if not os.path.exists(src):
        ardj.log.error('False start: %s not found.' % src)
        return False

    os.rename(src, dst)
    ardj.twitter.send_message(ardj.settings.get('stream/twit_begin', 'Somebody is on air!'))
    return True


def stop_stream(quiet):
    dirname = os.path.dirname(ardj.settings.getpath('stream/dump'))
    purge(dirname)
    filename = os.path.join(dirname, sorted([x for x in os.listdir(dirname) if x.endswith('.mp3')])[-1])
    twit_file(filename, quiet)
    update_rss(dirname)


def run_cli(args):
    """Implements the "ardj stream" command."""
    if len(args) and args[0] == 'start':
        return start_stream()
    if len(args) and args[0] == 'stop':
        return stop_stream('-quiet' in args)
    print USAGE
