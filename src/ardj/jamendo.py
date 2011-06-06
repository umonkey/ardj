# encoding=utf-8

"""Interface to Jamendo.

Contains the code to fetch missing tracks from Jamendo.
"""

import ardj.database
import ardj.settings
import ardj.util


def find_new_tracks(artist_names=None, verbose=False):
    """Returns tracks to fetch.  Result is a list of dictionaries with keys:
    artist, title, url, tags."""
    db = ardj.database.Open()
    cur = db.cursor()

    todo = []

    tags = ardj.settings.get('fresh_music/jamendo_tags', [ ])
    tags.append('source:jamendo.com')

    if not artist_names:
        label = ardj.settings.get('fresh_music/filter_tag', 'music')
        weight = ardj.settings.get('fresh_music/filter_weight', 1.5)
        artist_names = db.get_artist_names(label=label, weight=weight)

    for artist_name in artist_names:
        data = ardj.util.fetch_json(url='http://api.jamendo.com/get2/id+name+artist_name+stream/track/json/track_album+album_artist', args={
            'order': 'searchweight_desc',
            'n': '20',
            'artist_name': artist_name.encode('utf-8'),
            'streamencoding': 'ogg2',
        }, ret=True, quiet=True) or []
        for track in data:
            todo.append({
                'artist': track['artist_name'],
                'title': track['name'],
                'url': track['stream'],
                'suffix': '.ogg',
                'tags': tags,
            })
            if verbose:
                print u'- artist: %s' % track['artist_name']
                print u'   title: %s' % track['name']
                print u'     url: %s' % track['stream']
    return todo


def print_new_tracks(args):
    """Prints a sorted list of new tracks available at Jamendo."""
    find_new_tracks(args, verbose=True)
