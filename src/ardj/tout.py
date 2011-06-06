# vim: set fileencoding=utf-8:

import json
import os
import time

import ardj.database
import ardj.log
import ardj.settings
import ardj.scrobbler
import ardj.website

class LastFmError(Exception): pass


def get_artist_names():
    """Returns names of all artists that have well rated music."""
    cur = ardj.database.Open().cursor()
    return sorted([row[0] for row in cur.execute('SELECT DISTINCT artist FROM tracks WHERE id IN (SELECT track_id FROM labels WHERE label = ?) AND weight >= ?', (ardj.settings.get('tout/label', 'music'), float(ardj.settings.get('tout/weight', '1.0')), )).fetchall()])


def fetch_artist_events(lastfm, artist_name):
    """Requests fresh events from LastFM."""
    events = []

    try:
        print 'Updating %s' % artist_name.encode('utf-8')
        data = lastfm.get_events_for_artist(artist_name)

        if 'error' in data:
            raise LastFmError('Last.fm reports error: %s' % data['message'])

        if 'events' not in data:
            ardj.log.debug('Oops: %s had no "events" block -- no such artist?' % artist_name.encode('utf-8'))
            print data
            return []
        data = data['events']

        if 'artist' in data:
            artist_name = data['artist']
        elif '@attr' in data and 'artist' in data['@attr']:
            artist_name = data['@attr']['artist']

        if 'event' in data:
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
    """Returns events from LastFM.  Uses caching (12 hours by default)."""
    cache_fn = ardj.settings.getpath('tout/cache', '~/.config/ardj/events.json')

    if os.path.exists(cache_fn):
        if time.time() - os.stat(cache_fn).st_mtime < int(ardj.settings.get('tout/cache_ttl', '43200')):
            return json.loads(open(cache_fn, 'rb').read())

    lastfm = ardj.scrobbler.LastFM().authorize()

    events = []
    for artist_name in sorted(list(set([n.lower() for n in get_artist_names()]))):
        tmp = fetch_artist_events(lastfm, artist_name)
        if tmp is None:
            continue # wtf ?!
        events += tmp

    artist_names = list(set([e['artist'] for e in events if e.get('artist')]))
    update_labels(artist_names)

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
    ardj.log.info('Wrote %s' % filename)


def update_labels(artist_names):
    """Adds the concert-soon labels to appropriate tracks."""
    db = ardj.database.Open()
    cur = db.cursor()
    cur.execute("DELETE FROM labels WHERE label = 'concert-soon'")
    for name in artist_names:
        cur.execute('INSERT INTO labels (track_id, label, email) '
            'SELECT id, ?, ? FROM tracks WHERE artist = ?', (
            'concert-soon', 'ardj', name, ))
    db.commit()


def run_cli(args):
    """Implements the "ardj events" command."""
    if 'refresh' in args:
        fetch_events()

    if 'update-website' in args:
        if ardj.settings.get('tout/website_js'):
            update_website()
        else:
            ardj.log.debug('Not updating website: tout/website_js not set.')

    if not args:
        print 'Usage: ardj events refresh|update-website'
        return 1

    return 0
