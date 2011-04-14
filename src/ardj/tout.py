# vim: set fileencoding=utf-8:

import datetime
import json
import os
import random
import shutil
import sys
import subprocess
import tempfile
import time
import urllib
import urllib2
import wave

import ardj
import ardj.database
import ardj.settings
import ardj.website
import ardj.tags
import ardj.util
import ardj.log

class LastFmError(Exception): pass

def sox(args, suffix='.wav'):
    output_fn = ardj.util.mktemp(suffix=suffix)
    args = [(arg == 'OUTPUT') and output_fn or arg for arg in args]
    args.insert(0, 'sox')
    ardj.util.run(args)
    return output_fn


def get_artist_names():
    cur = ardj.database.Open().cursor()
    return sorted([row[0] for row in cur.execute('SELECT DISTINCT artist FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) AND weight >= ?', (ardj.settings.get('tout/label', 'music'), float(ardj.settings.get('tout/weight', '1.0')), )).fetchall()])

def fetch_artist_events(artist_name):
    events = []

    try:
        url = 'http://ws.audioscrobbler.com/2.0/?method=artist.getEvents&artist=%s&api_key=%s&format=json&autocorrect=1' % (urllib.quote(artist_name.encode('utf-8')), ardj.settings.get('last.fm/key'))
        data = json.loads(ardj.util.fetch(url, ret=True))

        if 'error' in data:
            raise LastFmError('Last.fm reports error: %s' % data['message'])

        if not data.has_key('events'):
            ardj.log.debug('Oops: %s had no "events" block -- no such artist?' % artist_name.encode('utf-8'))
            print data
            return []
        data = data['events']

        if data.has_key('artist'):
            artist_name = data['artist']
        elif data.has_key('@attr') and data['@attr'].has_key('artist'):
            artist_name = data['@attr']['artist']

        if data.has_key('event'):
            for event in (type(data['event']) == list) and data['event'] or [data['event']]:
                if event['cancelled'] != '0':
                    continue
                events.append({
                    'id': int(event['id']),
                    'artist': artist_name,
                    'startDate': time.strftime('%Y-%m-%d', time.strptime(event['startDate'][:16], '%a, %d %b %Y')),
                    'url': event['url'],
                    'country': event['venue']['location']['country'],
                    'city': event['venue']['location']['city'],
                    'venue': event['venue']['name'],
                    'venue_url': event['venue']['url'],
                    'venue_location': event['venue']['location']['geo:point'],
                })
    except LastFmError, e:
        ardj.log.error('Fatal: %s' % e)
        return None
    except Exception, e:
        ardj.log.error('ERROR fetching events for %s: %s' % (artist_name.encode('utf-8'), e))
    return events

def fetch_events():
    cache_fn = ardj.settings.getpath('tout/cache', '~/.config/ardj/events.json')

    if os.path.exists(cache_fn):
        if time.time() - os.stat(cache_fn).st_mtime < int(ardj.settings.get('tout/cache_ttl', '3600')):
            return json.loads(open(cache_fn, 'rb').read())

    events = []
    for artist_name in sorted(list(set([n.lower() for n in get_artist_names()]))):
        tmp = fetch_artist_events(artist_name)
        if tmp is None:
            return None
        events += tmp

    open(cache_fn, 'wb').write(json.dumps(events))
    return events

def update_website():
    data = { 'bounds': [], 'markers': [] }
    events = fetch_events()
    if events is None:
        return
    for event in events:
        if event['venue_location']['geo:long'] and event['venue_location']['geo:lat']:
            data['markers'].append({
                'll': [float(event['venue_location']['geo:lat']), float(event['venue_location']['geo:long'])],
                'html': u'<p><strong>%s</strong><br/>%s, %s<br/>%s</p><p class="more"><a href="%s" target="_blank">Подробности</a></p>' % (event['artist'], event['venue'], event['city'], '.'.join(reversed(event['startDate'].split('-'))), event['url']),
            })
    data['bounds'].append(min([e['ll'][0] for e in data['markers']]))
    data['bounds'].append(max([e['ll'][0] for e in data['markers']]))
    data['bounds'].append(min([e['ll'][1] for e in data['markers']]))
    data['bounds'].append(max([e['ll'][1] for e in data['markers']]))

    filename = ardj.settings.getpath('tout/website_js', '~/.config/ardj/event-map.js')
    output = 'var map_data = %s;' % json.dumps(data, indent=True)
    open(filename, 'wb').write(output)
    ardj.info('Wrote %s' % filename)

    ardj.website.update('update-map')

def get_announce_text():
    u"Возвращает текст для диктовки роботом."
    data = {}
    date_limit = time.strftime('%Y-%m-%d', time.localtime(time.time() + int(ardj.settings.get('tout/announce_time_limit', 86400*14))))

    countries = ardj.settings.get('tout/announce_countries')
    for event in fetch_events():
        if not countries or event['country'] in countries:
            date = event['startDate']
            if date < date_limit:
                city = event['city'].split(',')[0]
                if not data.has_key(date):
                    data[date] = {}
                if not data[date].has_key(city):
                    data[date][city] = []
                if event['artist'] not in data[date][city]:
                    data[date][city].append(event['artist'])

    output = ardj.settings.get('tout/announce_prefix', u'').strip() + u'\n\n'
    for date in sorted(data.keys()):
        output += xlat_date(date) + u'.\n'
        for city in sorted(data[date].keys()):
            output += xlat_city(city)
            for artist in sorted(data[date][city]):
                output += u', ' + xlat_artist(artist)
            output += u'.\n\n'
    output += ardj.settings.get('tout/announce_suffix', u'')
    return output.strip()

def update_announce():
    text_fn = ardj.util.mktemp(suffix='.txt')
    open(str(text_fn), 'wb').write(get_announce_text().encode('utf-8'))
    ardj.log.debug('Wrote speech text to %s' % text_fn)

    speech_fn = ardj.util.mktemp(suffix='.wav')
    ardj.util.run(['text2wave', '-eval', '(voice_msu_ru_nsh_clunits)', str(text_fn), '-o', str(speech_fn)]).wait()
    ardj.log.debug('Wrote speech wave to %s' % speech_fn)

    speech_fn = sox([ speech_fn, '-r', '44100', '-c', '2', 'OUTPUT', 'pad', '3', '5'] )
    length = get_wav_length(str(speech_fn))
    ardj.log.debug('Resampled speech length is %u seconds.' % length)

    if ardj.settings.get('tout/background'):
        background_fn = get_background_fn(length)
        if background_fn:
            speech_fn = sox([ '--combine', 'mix-power', '-v', '0.25', background_fn, str(speech_fn), 'OUTPUT' ])

    result_fn = sox([ speech_fn, 'OUTPUT' ], suffix='.ogg')
    ardj.log.debug('Wrote result to %s' % result_fn)

    target_fn = ardj.settings.getpath('tout/announce_file')
    if os.path.exists(target_fn):
        os.unlink(target_fn)
        shutil.move(result_fn, target_fn)
        result_fn = target_fn

    track_id = int(ardj.settings.get('tout/track_id', '0'))
    if track_id:
        length = ardj.tags.raw(result_fn).info.length
        ardj.database.Open().cursor().execute('UPDATE tracks SET length = ? WHERE id = ?', (length, track_id, ))

def get_wav_length(filename):
    f = wave.open(filename, 'r')
    return f.getnframes() / f.getframerate()

def get_background_fn(length):
    filename = ardj.settings.getpath('tout/announce_background', '~/this file should not exist')
    if not os.path.exists(filename):
        cur = ardj.database.Open().cursor()
        tracks = sorted([row[0] for row in cur.execute('SELECT filename FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) ORDER BY weight DESC LIMIT 10', (ardj.settings.get('tout/background_label', ardj.settings.get('tout/label', 'music')), )).fetchall()])
        if not len(tracks):
            return None
        filename = os.path.join(ardj.settings.get_music_dir(), tracks[random.randrange(0, len(tracks))])
    if not os.path.exists(filename):
        return None
    return sox([ filename, '-r', '44100', '-c', '2', 'OUTPUT', 'trim', '0', str(length) ])

def xlat_date(date):
    months = [u'января', u'февраля', u'марта', u'апреля', u'мая', u'июня', u'июля', u'августа', u'сентября', u'октября', u'ноября', u'декабря']
    days = [u'Первого', u'Второго', u'Третьего', u'Четвёртого', u'Пятого', u'Шестого', u'Седьмого', u'Восьмого', u'Девятого', u'Десятого', u'Одиннадцатого', u'Двенадцатого', u'Тринадцатого', u'Четырнадцатого', u'Пятнадцатого', u'Шестнадцатого', u'Семнадцатого', u'Восемнадцатого', u'Девятнадцатого', u'Двадцатого', u'Двадцать первого', u'Двадцать второго', u'Двадцать третьего', u'Двадцать четвёртого', u'Двадцать пятого', u'Двадцать шестого', u'Двадцать седьмого', u'Двадцать восьмого', u'Двадцать девятого', u'Тридцатого', u'Тридцать первого']

    date = datetime.datetime.strptime(date, '%Y-%m-%d')
    output = u'%s %s' % (days[date.day - 1], months[date.month - 1])

    return output

def xlat_city(city):
    table = ardj.settings.get('tout/city_map', {})
    if table.has_key(city):
        return table[city]
    return city

def xlat_artist(artist):
    table = ardj.settings.get('tout/artist_map', {})
    if table.has_key(artist):
        return table[artist]
    return artist


def run_cli(args):
    """Implements the "ardj events" command."""
    if ardj.settings.get('tout/website_js'):
        update_website()
    else:
        ardj.log.debug('Not updating website: tout/website_js not set.')
    if ardj.settings.get('tout/announce_file'):
        update_announce()
    else:
        ardj.log.debug('Not updating the speech: tout/announce_file not set.')