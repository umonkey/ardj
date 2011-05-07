import hashlib
import json

import ardj.log
import ardj.settings
import ardj.util


class LastFM(object):
    """The LastFM client."""
    ROOT = 'http://ws.audioscrobbler.com/2.0/'

    def __init__(self):
        self.key = ardj.settings.get('last.fm/key')
        self.secret = ardj.settings.get('last.fm/secret')
        self.login = ardj.settings.get('last.fm/login')
        self.password = ardj.settings.get('last.fm/password')
        self.sk = None

    def authorize(self):
        """Authorizes for a session key as a mobile device.
        Details: http://www.last.fm/api/mobileauth"""
        data = self.call(method='auth.getMobileSession',
            username=self.login,
            authToken=self.get_auth_token(),
            api_sig=True
        )
        self.sk = str(data['session']['key'])
        if self.sk:
            ardj.log.info('Successfully authenticated with Last.FM')
        return self

    def scrobble(self, artist, title, ts):
        """Scrobbles a track.  If there's no session key (not authenticated),
        does nothing."""
        if self.sk:
            data = self.call(method='track.scrobble',
                artist=artist.encode('utf-8'),
                track=title.encode('utf-8'),
                timestamp=str(ts), api_sig=True, sk=self.sk,
                post=True)
            ardj.log.info(u'Sent to last.fm: %s -- %s' % (artist, title))
            return True

    def now_playing(self, artist, title):
        """Tells LastFM what you're listening to."""
        if self.sk:
            self.call(method='track.UpdateNowPlaying',
                artist=artist, title=title,
                api_sig=True, sk=self.sk,
                post=True)

    def love(self, artist, title):
        if self.sk:
            data = self.call(method='track.love',
                artist=artist.encode('utf-8'),
                track=title.encode('utf-8'),
                api_sig=True,
                sk=self.sk,
                post=True)
            if 'error' in data:
                ardj.log.info(u'Could not love a track with last.fm: %s' % data['message'])
                return False
            else:
                ardj.log.info(u'Sent to last.fm love for: %s -- %s' % (artist, title))
                return True

    def get_events_for_artist(self, artist_name):
        """Lists upcoming events for an artist."""
        return self.call(method='artist.getEvents',
            artist=artist_name.encode('utf-8'),
            autocorrect='1')

    def process(self, cur):
        """Looks for stuff to scrobble in the playlog table."""
        skip_labels = ardj.settings.get('last.fm/skip_labels')
        if skip_labels:
            in_sql = ', '.join(['?'] * len(skip_labels))
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY p.ts' % in_sql
            params = skip_labels
        else:
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 ORDER BY p.ts'
            params = []
        rows = cur.execute(sql, params).fetchall()
        if rows:
            print sql, params
        for artist, title, ts in rows:
            if not self.scrobble(artist, title, ts):
                return False
            cur.execute('UPDATE playlog SET lastfm = 1 WHERE ts = ?', (ts, ))
        return True

    def call(self, post=False, api_sig=False, **kwargs):
        kwargs['api_key'] = self.key
        if api_sig:
            kwargs['api_sig'] = self.get_call_signature(kwargs)
        kwargs['format'] = 'json'
        raw_response = ardj.util.fetch(self.ROOT, args=kwargs, post=post, quiet=True, ret=True)
        if raw_response:
            return json.loads(raw_response)

    def get_call_signature(self, args):
        parts = sorted([''.join(x) for x in args.items()])
        return hashlib.md5(''.join(parts) + self.secret).hexdigest()

    def get_auth_token(self):
        """Returns a hex digest of the MD5 sum of the user credentials."""
        pwd = hashlib.md5(self.password).hexdigest()
        return hashlib.md5(self.login.lower() + pwd).hexdigest()
