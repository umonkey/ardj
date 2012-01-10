# encoding=utf-8

"""Interface to Jamendo.

Contains the code to fetch missing tracks from Jamendo.
"""

import ardj.database
import ardj.settings
import ardj.util


def get_track_info(artist_name, track_title):
    data = ardj.util.fetch_json(url='http://api.jamendo.com/get2/id+name+artist_name+stream/track/json/track_album+album_artist/', args={
        'n': 'all',
        'artist_name': artist_name.encode('utf-8'),
        'track_name': track_title.encode('utf-8'),
        'streamencoding': 'ogg2',
    }, ret=True, quiet=True)

    if data:
        return data[0]


def find_new_tracks(artist_names=None, verbose=False):
    """Returns tracks to fetch.  Result is a list of dictionaries with keys:
    artist, title, url, tags."""
    db = ardj.database.Open()

    todo = []

    tags = ardj.settings.get('fresh_music/tags', [])

    if not artist_names:
        label = ardj.settings.get('fresh_music/filter_tag', 'music')
        weight = ardj.settings.get('fresh_music/filter_weight', 1.5)
        artist_names = db.get_artist_names(label=label, weight=weight)

    for artist_name in artist_names:
        data = ardj.util.fetch_json(url='http://api.jamendo.com/get2/id+name+artist_name+stream/track/json/track_album+album_artist/', args={
            'n': 'all',
            'artist_name': artist_name.encode('utf-8'),
            'streamencoding': 'ogg2',
        }, ret=True, quiet=True) or []
        for track in data:
            if not track.get('stream'):
                continue
            todo.append({
                'artist': artist_name,
                'title': track['name'],
                'url': track['stream'],
                'suffix': '.ogg',
                'tags': tags + ['source:jamendo.com'],
            })
            if verbose:
                print u'- artist: %s' % track['artist_name']
                print u'   title: %s' % track['name']
                print u'     url: %s' % track['stream']
    return todo


def print_new_tracks(args):
    """Prints a sorted list of new tracks available at Jamendo."""
    todo = find_new_tracks(args, verbose=True)
    if todo:
        return

    if args:
        print "Could not find anything new in Jamendo.  This probably means that Jamendo has no new music for %s." % args
    else:
        print "Could not find anything new in Jamendo.  This probably means that Jamendo has no new music for the artists from your database."
