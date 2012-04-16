# vim: set fileencoding=utf-8:

import json
import logging
import os
import sys
import time

import ardj.database
import ardj.settings
import ardj.scrobbler
import ardj.website


def get_artist_names():
    """Returns names of all artists that have well rated music."""
    label = ardj.settings.get("event_schedule_label_filter", "music")
    weight = float(ardj.settings.get("event_schedule_label_weight", "1.0"))

    rows = ardj.database.fetch("SELECT DISTINCT artist "
        "FROM tracks WHERE id IN (SELECT track_id FROM labels "
        "WHERE label = ?) AND weight >= ?", (label, weight, ))
    return sorted([row[0] for row in rows])


def fetch_artist_events(lastfm, artist_name):
    """Requests fresh events from LastFM."""
    events = []

    try:
        print 'Updating %s' % artist_name.encode('utf-8')
        data = lastfm.get_events_for_artist(artist_name)
        if not data:
            logging.warning('Could not fetch events for %s.' % artist_name.encode("utf-8"))

        if 'events' not in data:
            logging.debug('Oops: %s had no "events" block -- no such artist?' % artist_name.encode('utf-8'))
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
    except ardj.scrobbler.BadAuth:
        raise
    except ardj.scrobbler.Error, e:
        logging.warning("Could not fetch events for %s: %s" % (artist_name.encode("utf-8"), e))
        return []
    except Exception, e:
        logging.error('%s error fetching events for %s: %s' % (type(e).__name__, artist_name.encode('utf-8'), e))
    return events


def fetch_events(refresh=False):
    """Returns events from LastFM.  Uses caching (12 hours by default)."""
    cache_fn = ardj.settings.getpath("event_schedule_cache", "/tmp/ardj-events-cache.json")

    if os.path.exists(cache_fn):
        ttl = int(ardj.settings.get("event_schedule_cache_ttl", "43200"))
        if time.time() - os.stat(cache_fn).st_mtime < ttl and not refresh:
            logging.debug("Event schedule read from cache (%s, younger than %u sec)" % (cache_fn, ttl))
            return json.loads(open(cache_fn, 'rb').read())

    lastfm = ardj.scrobbler.LastFM().authorize()

    events = []
    for artist_name in sorted(list(set([n.lower() for n in get_artist_names()]))):
        tmp = fetch_artist_events(lastfm, artist_name)
        if tmp is None:
            continue  # wtf ?!
        events += tmp

    open(cache_fn, 'wb').write(json.dumps(events))

    artist_names = list(set([e['artist'] for e in events if e.get('artist')]))
    update_labels(artist_names)

    return events


def update_website(filename):
    data = {"bounds": [], "markers": []}

    events = fetch_events()
    if events is None:
        return

    for event in events:
        if event['venue_location']['geo:long'] and event['venue_location']['geo:lat']:
            data['markers'].append({
                'll': [float(event['venue_location']['geo:lat']), float(event['venue_location']['geo:long'])],
                'html': u'<p><strong>%s</strong><br/>%s, %s<br/>%s</p><p class="more"><a href="%s" target="_blank">Подробности</a></p>' % (event['artist'], event['venue'], event['city'], '.'.join(reversed(event['startDate'].split('-'))), event['url']),
            })

    if data["markers"]:
        data['bounds'].append(min([e['ll'][0] for e in data['markers']]))
        data['bounds'].append(max([e['ll'][0] for e in data['markers']]))
        data['bounds'].append(min([e['ll'][1] for e in data['markers']]))
        data['bounds'].append(max([e['ll'][1] for e in data['markers']]))

    output = 'var map_data = %s;' % json.dumps(data, indent=True)
    open(filename, 'wb').write(output)
    logging.info('Wrote event schedule to %s' % filename)


def update_labels(artist_names):
    """Adds the concert-soon labels to appropriate tracks."""
    ardj.database.execute("DELETE FROM labels WHERE label = 'concert-soon'")
    for name in artist_names:
        logging.debug("Tagging %s with concert-soon" % name.encode("utf-8"))
        ardj.database.execute('INSERT INTO labels (track_id, label, email) '
            'SELECT id, ?, ? FROM tracks WHERE artist = ?', (
            'concert-soon', 'ardj', name, ))


def update_schedule(refresh=False):
    """Updates the event schedule."""
    try:
        fetch_events(refresh)
    except ardj.scrobbler.Error, e:
        print >> sys.stderr, "Last.fm error:", e
        return False

    event_schedule_path = ardj.settings.get("event_schedule_path")
    if not event_schedule_path:
        logging.warning("No event_schedule_path, not updating the schedule.")
        return False

    update_website(event_schedule_path)
