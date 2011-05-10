import hashlib
import json
import time

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
        does nothing.  Returns True on success."""
        if not ardj.settings.get('last.fm/scrobble', True):
            return True
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
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.length > 60 AND t.id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY p.ts' % in_sql
            params = skip_labels
        else:
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.length > 60 ORDER BY p.ts'
            params = []
        rows = cur.execute(sql, params).fetchall()
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


class LibreFM(object):
    # http://amarok.kde.org/wiki/Scrobbling_to_Libre.fm
    ROOT = 'http://turtle.libre.fm/'

    def __init__(self):
        self.login = ardj.settings.get('libre.fm/login')
        self.password = ardj.settings.get('libre.fm/password')
        self.submit_url = None
        self.session_key = None

    def authorize(self):
        """Connects to the libre.fm server."""
        if self.login:
            data = ardj.util.fetch(self.ROOT, args={
                'hs': 'true',
                'p': '1.1',
                'c': 'lsd',
                'v': '1.0',
                'u': self.login,
            }, quiet=True, ret=True)
            parts = data.split('\n')
            if parts[0] != 'UPTODATE':
                ardj.log.error('Could not log to libre.fm: %s' % parts[0])
                return False
            else:
                self.submit_url = parts[2].strip()
                self.session_key = self.get_session_key(parts[1].strip())
                ardj.log.debug('Logged in to libre.fm, will submit to %s' % (self.submit_url, ))
                return True

    def scrobble(self, artist, title, ts=None, retry=True):
        """Scrobbles a track, returns True on success."""
        if not ardj.settings.get('libre.fm/scrobble', True):
            return True
        if ts is None:
            ts = int(time.time())
        args = {
            'u': self.login,
            's': self.session_key,
            'a[0]': artist.encode('utf-8'),
            't[0]': title.encode('utf-8'),
            'i[0]': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts)),
        }
        data = ardj.util.fetch(self.submit_url, args=args, post=True, ret=True).strip()
        if data == 'OK':
            ardj.log.debug(u'Sent to libre.fm: %s -- %s' % (artist, title))
            return True
        elif data == 'BADSESSION' and retry:
            ardj.log.debug('Bad libre.fm session, renewing.')
            self.authorize()
            return self.scrobble(artist, title, ts, False)
        else:
            ardj.log.error('Could not submit to libre.fm: %s' % data)
            return False

    def process(self, cur):
        """Looks for stuff to scrobble in the playlog table."""
        skip_labels = ardj.settings.get('libre.fm/skip_labels',
            ardj.settings.get('last.fm/skip_labels'))
        if skip_labels:
            in_sql = ', '.join(['?'] * len(skip_labels))
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.librefm = 0 AND t.weight > 0 AND t.length > 60 AND t.id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY p.ts' % in_sql
            params = skip_labels
        else:
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.librefm = 0 AND t.weight > 0 AND t.length > 60 ORDER BY p.ts'
            params = []
        rows = cur.execute(sql, params).fetchall()[:10]
        for artist, title, ts in rows:
            if not self.scrobble(artist, title, ts):
                return False
            cur.execute('UPDATE playlog SET librefm = 1 WHERE ts = ?', (ts, ))
        return True

    def get_session_key(self, challenge):
        """Returns a session key which consists of the challenge and user's password."""
        if not self.password:
            return None
        tmp = hashlib.md5(self.password).hexdigest()
        return hashlib.md5(tmp + challenge).hexdigest()
