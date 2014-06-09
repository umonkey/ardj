import hashlib
import logging
import time

import ardj.database
import ardj.settings
import ardj.util


class Error(Exception):
    """Scrobbling errors."""
    pass


class BadAuth(Error):
    """Thrown when the configured credentials are wrong."""
    pass


class InvalidParameters(Error):
    pass


class TrackNotFound(Error):
    pass


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
        if not self.login or not self.password or not self.key or not self.secret:
            logging.debug("Last.fm disabled -- not enough configuration.")
            return self

        try:
            data = self.call(method='auth.getMobileSession',
                username=self.login,
                authToken=self.get_auth_token(),
                api_sig=True)
        except Exception, e:
            logging.error("Last.fm authentication failure: %s" % e)
            data = None
        if not data:
            logging.error('Could not authenticate with last.fm: no data.')
            return None
        else:
            self.sk = str(data['session']['key'])
            if self.sk:
                logging.info('Successfully authenticated with Last.FM')
        return self

    def scrobble(self, artist, title, ts):
        """Scrobbles a track.  If there's no session key (not authenticated),
        does nothing.  Returns True on success."""
        if not self.is_enabled():
            return True
        if self.sk is None and not self.authorize():
            return False
        if self.sk:
            data = self.call(method='track.scrobble',
                artist=artist.encode('utf-8'),
                track=title.encode('utf-8'),
                timestamp=str(ts), api_sig=True, sk=self.sk,
                post=True)
            logging.info((u'Sent to last.fm: %s -- %s' % (artist, title)).encode("utf-8"))
            return True

    def is_enabled(self):
        return ardj.settings.get("last_fm_scrobble", ardj.settings.get("last.fm/scrobble", False))

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
                logging.info("Could not love a track with last.fm: %s" % data["message"].encode("utf-8"))
                return False
            else:
                logging.info(("Sent to last.fm love for: %s -- %s" % (artist, title)).encode("utf-8"))
                return True

    def get_events_for_artist(self, artist_name):
        """Lists upcoming events for an artist."""
        return self.call(method='artist.getEvents',
            artist=artist_name.encode('utf-8'),
            autocorrect='1')

    def get_artist_info(self, artist_name):
        logging.debug("Retrieving last.fm info for %s" % (artist_name.encode("utf-8")))
        return self.call_signed(method="artist.getInfo",
            artist=artist_name.encode("utf-8"))

    def get_artist_tags(self, artist_name):
        """Returns top tags for the specified artist."""
        data = self.get_artist_info(artist_name)

        if "artist" not in data or type(data["artist"]) != dict:
            return []
        data = data["artist"]

        if "tags" not in data or type(data["tags"]) != dict:
            return []
        data = data["tags"]

        if "tag" not in data or type(data["tag"]) != list:
            return []
        data = data["tag"]

        return [t["name"] for t in data]

    def get_track_info(self, artist_name, track_title):
        logging.debug((u"Retrieving last.fm info for \"%s\" by %s" % (track_title, artist_name)).encode("utf-8"))
        return self.call_signed(method="track.getInfo",
            artist=artist_name.encode("utf-8"),
            track=track_title.encode("utf-8"),
            autocorrect="1")

    def get_track_info_ex(self, artist_name, track_title):
        info = {"artist": artist_name, "title": track_title, "tags": [], "image": None, "download": None}

        data = self.get_track_info(artist_name, track_title)
        if "track" not in data:
            return info
        data = data["track"]

        def listify(x):
            if not isinstance(x, list):
                x = [x]
            return x

        if "artist" in data:
            info["artist"] = data["artist"]

        if "name" in data:
            info["title"] = data["name"]

        if "album" in data and "image" in data["album"]:
            image = listify(data["album"]["image"])
            for img in image:
                if img["size"] == "small":
                    info["image"] = img["#text"]
                    break

        if "freedownload" in data:
            info["download"] = data["freedownload"]

        if "toptags" in data and "tag" in data["toptags"]:
            for tag in listify(data["toptags"]["tag"]):
                info["tags"].append(tag["name"])

        info["tags"] += self.get_artist_tags(artist_name)
        info["tags"] = list(set(info["tags"]))

        return info

    def is_artist(self, name):
        try:
            data = self.call_signed(method="artist.getInfo",
                artist=name.encode("utf-8"))
            return True
        except Exception, e:
            logging.error("Could not find artist: %s" % e)
            return False

    def get_track_tags(self, artist_name, track_title):
        """Returns top tags for the specified track."""
        data = self.get_track_info(artist_name, track_title)

        for k in "track", "toptags", "tag":
            if k not in data or not isinstance(data[k], (dict, list)):
                return []
            data = data[k]

        if type(data) == dict:
            data = [data]

        return [t["name"] for t in data]

    def get_tracks_by_artist(self, artist_name):
        tags = ardj.settings.get('fresh_music/tags', [])

        try:
            data = self.call(method='artist.getTopTracks',
                artist=artist_name.encode('utf-8'),
                limit=1000)
        except InvalidParameters:
            return []

        if 'toptracks' not in data:
            return []
        if 'track' not in data['toptracks']:
            return []

        result = []
        for t in data['toptracks']['track']:
            if 'downloadurl' in t:
                result.append({
                    'artist': t['artist']['name'],
                    'title': t['name'],
                    'url': t['downloadurl'],
                    'tags': tags + ['source:last.fm'],
                })
        return result

    def get_corrected_name(self, artist_name):
        data = self.call(method='artist.getCorrection',
            artist=artist_name.encode('utf-8'))
        try:
            return data['corrections']['correction']['artist']['name']
        except KeyError:
            pass
        except TypeError:
            pass
        return None

    def process(self):
        """Looks for stuff to scrobble in the playlog table."""
        skip_labels = ardj.settings.get('last.fm/skip_labels', ardj.settings.get("last_fm_skip_labels"))
        if skip_labels:
            in_sql = ', '.join(['?'] * len(skip_labels))
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.length > 60 AND t.id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY p.ts' % in_sql
            params = skip_labels
        else:
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.length > 60 ORDER BY p.ts'
            params = []
        rows = ardj.database.fetch(sql, params)
        for artist, title, ts in rows:
            if not self.scrobble(artist, title, ts):
                return False
            ardj.database.execute('UPDATE playlog SET lastfm = 1 WHERE ts = ?', (ts, ))
            ardj.database.commit()  # prevent hanging transactions
        return True

    def call(self, post=False, api_sig=False, **kwargs):
        if self.key is None:
            raise BadAuth("Unable to call last.fm: no API key")
        kwargs['api_key'] = self.key
        if api_sig:
            kwargs['api_sig'] = self.get_call_signature(kwargs)
        kwargs['format'] = 'json'
        response = ardj.util.fetch_json(self.ROOT, args=kwargs, post=post, quiet=True, ret=True)
        if response is None:
            raise Error("Empty response")
        if "error" in response:
            logging.error("Last.fm error %u: %s" % (response["error"], response["message"]))
            if response["error"] in (4, 9, 10, 13, 26):
                raise BadAuth(response["message"])
            if response["error"] == 6 and response["message"] == "Track not found":
                raise TrackNotFound(response["message"])
            if response["error"] == 6:
                raise InvalidParameters(response["message"])
            raise Error(response["message"])
        return response

    def call_signed(self, post=False, **kwargs):
        if self.sk is None:
            self.authorize()
        kwargs["sk"] = self.sk
        return self.call(post=post, api_sig=True, **kwargs)

    def get_call_signature(self, args):
        skip_fields = "format", "callback"
        parts = sorted([''.join(x) for x in args.items() if x[0] not in skip_fields])
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
            if data is None:
                logging.error("Empty response from libre.fm")
                return False
            parts = data.split('\n')
            if parts[0] != 'UPTODATE':
                logging.error('Could not log to libre.fm: %s' % parts[0])
                return False
            else:
                self.submit_url = parts[2].strip()
                self.session_key = self.get_session_key(parts[1].strip())
                logging.debug('Logged in to libre.fm, will submit to %s' % (self.submit_url, ))
                return True

    def scrobble(self, artist, title, ts=None, retry=True):
        """Scrobbles a track, returns True on success."""
        if not self.is_enabled():
            return True
        if self.submit_url is None and not self.authorize():
            return False
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
        if data is None:
            logging.error("Empty response from libre.fm")
            return False
        if data == 'OK':
            logging.debug((u'Sent to libre.fm: %s -- %s' % (artist, title)).encode("utf-8"))
            return True
        elif data == 'BADSESSION' and retry:
            logging.debug('Bad libre.fm session, renewing.')
            self.authorize()
            return self.scrobble(artist, title, ts, False)
        else:
            logging.error('Could not submit to libre.fm: %s' % data)
            return False

    def is_enabled(self):
        return ardj.settings.get("libre_fm_scrobble", ardj.settings.get("libre.fm/scrobble", True))

    def process(self):
        """Looks for stuff to scrobble in the playlog table."""
        if not ardj.settings.get("libre_fm_scrobble"):
            return

        skip_labels = ardj.settings.get("libre_fm_skip_labels", ardj.settings.get("last_fm_skip_labels"))
        if skip_labels:
            in_sql = ', '.join(['?'] * len(skip_labels))
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.librefm = 0 AND t.weight > 0 AND t.length > 60 AND t.id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY p.ts' % in_sql
            params = skip_labels
        else:
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.librefm = 0 AND t.weight > 0 AND t.length > 60 ORDER BY p.ts'
            params = []
        rows = ardj.database.fetch(sql, params)[:10]
        for artist, title, ts in rows:
            if not self.scrobble(artist, title, ts):
                return False
            ardj.database.execute('UPDATE playlog SET librefm = 1 WHERE ts = ?', (ts, ))
            ardj.database.commit()  # prevent hanging transactions
        return True

    def get_session_key(self, challenge):
        """Returns a session key which consists of the challenge and user's password."""
        if not self.password:
            return None
        tmp = hashlib.md5(self.password).hexdigest()
        return hashlib.md5(tmp + challenge).hexdigest()


def cmd_start():
    """Start the scrobbler process"""

    lastfm = LastFM()
    librefm = LibreFM()

    logging.info("Scrobbler started.")

    while True:
        lastfm.process()
        librefm.process()
        time.sleep(60)
