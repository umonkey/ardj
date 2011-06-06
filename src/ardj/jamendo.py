# encoding=utf-8

"""Interface to Jamendo.

Contains the code to fetch missing tracks from Jamendo.
"""

import ardj.database
import ardj.tracks
import ardj.util


def find_new_tracks(artist_names=None, verbose=False):
    """Returns tracks to fetch.  Result is a list of dictionaries with keys:
    artist, title, url, tags."""
    db = ardj.database.Open()
    cur = db.cursor()

    todo = []

    if not artist_names:
        artist_names = db.get_artist_names('music', weight=1.5)

    for artist_name in artist_names:
        data = ardj.util.fetch_json(url='http://api.jamendo.com/get2/id+name+artist_name+stream/track/json/track_album+album_artist', args={
            'order': 'searchweight_desc',
            'n': '20',
            'artist_name': artist_name.encode('utf-8'),
            'streamencoding': 'ogg2',
        }, ret=True, quiet=True)
        for track in data:
            if not ardj.tracks.find_by_title(track['name'], track['artist_name'], cur=cur):
                todo.append({
                    'artist': track['artist_name'],
                    'title': track['name'],
                    'url': track['stream'],
                    'suffix': '.ogg',
                })
                if verbose:
                    print u'- artist: %s' % track['artist_name']
                    print u'   title: %s' % track['name']
                    print u'     url: %s' % track['stream']
    return todo


def print_new_tracks(args):
    """Prints a sorted list of new tracks available at Jamendo."""
    find_new_tracks(args, verbose=True)
