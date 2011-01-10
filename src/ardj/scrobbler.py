# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:

import csv
import datetime
import logging
import re
import sys
import time
import urllib2

try:
    import lastfm.client
    have_cli = True
except ImportError:
    have_cli = False

class client:
    """
    Last.fm client class. Uses lastfmsubmitd to send track info. Uses config
    file parameter lastfm/skip as a regular expression to match files that
    must never be reported (such as jingles).
    """
    def __init__(self, config):
        """
        Imports and initializes lastfm.client, reads options from bot's config file.
        """
        self.config = config
        self.skip_files = None
        self.skip_labels = self.config.get('lastfm/skip_labels', [])
        self.folder = self.config.get_music_dir()
        if have_cli:
            self.cli = lastfm.client.Daemon('ardj')
            self.cli.open_log()
        else:
            logging.warning('Scrobbler disabled: please install lastfmsubmitd.')
            self.cli = None
        skip = self.config.get('lastfm/skip_files', '')
        if skip:
            self.skip_files = re.compile(skip)

        # RegExp for get_listener_count().
        stats_re = self.config.get('icecast_stats/re', '<listeners>(\d+)</listeners>')
        if not stats_re: self.stats_re = None
        else: self.stats_re = re.compile(stats_re)

    def submit(self, track):
        """
        Reports a track, which must be a dictionary containing keys: file,
        artist, title. If a key is not there, the track is not reported.
        """
        if self.cli is not None:
            try:
                if self.__skip_filename(track):
                    pass
                elif self.__skip_labels(track):
                    pass
                elif track['artist'] and track['title']:
                    data = { 'artist': track['artist'].strip(), 'title': track['title'].strip(), 'time': time.gmtime(), 'length': track['length'] }
                    self.cli.submit(data)
                    self.log_track(track)
                    logging.info('scrobbler: sent "%s" by %s' % (data['title'].encode('utf-8'), data['artist'].encode('utf-8')))
                else:
                    logging.warning('scrobbler: no tags in %s' % track['filename'].encode('utf-8'))
            except KeyError, e:
                logging.error(u'scrobbler: no %s in %s' % (e.args[0], track))

    def __skip_filename(self, track):
        """
        Returns True if the track has a forbidden filename.
        """
        if self.skip_files is None:
            return False
        if self.skip_files.match(track['filename']):
            logging.info(u'scrobbler: skipped %s (forbidden file name)' % track['filename'])
            return True
        return False

    def __skip_labels(self, track):
        """
        Returns True if the track has a label which forbids scrobbling.
        """
        if not self.skip_labels:
            return False
        if not track.has_key('labels'):
            return False
        for label in self.skip_labels:
            if label in track['labels']:
                logging.info('scrobbler: skipped %s (forbidden label: %s)' % (track['filename'], label))
                return True
        return False

    def log_track(self, track):
        logname = self.config.get('listener_log', None)
        if logname is not None:
            lc = self.get_listener_count()
            if lc > 0:
                date = datetime.datetime.now()
                row = [date.strftime('%Y-%m-%d %H:%M:%S'), track['id'], track['artist'].encode('utf-8'), track['title'].encode('utf-8'), self.get_listener_count()]

                f = open(logname, 'a')
                c = csv.writer(f)
                c.writerow(row)
                f.close()

    def get_listener_count(self):
        """
        Returns the current listener count.

        Connects to the icecast2 administrative UI using http basic auth.
        Returns an integer, -1 in case of errors.
        """
        stats_url = self.config.get('icecast_stats/url', None)
        stats_user = self.config.get('icecast_stats/login', None)
        stats_pass = self.config.get('icecast_stats/password', None)

        if stats_url is None:
            logging.debug('Unable to count listeners: icecast_stats/url not defined.')
            return -1

        if stats_user and stats_pass:
            pm = urllib2.HTTPPasswordMgrWithDefaultRealm()
            pm.add_password(None, stats_url, stats_user, stats_pass)

            ah = urllib2.HTTPBasicAuthHandler(pm)
            opener = urllib2.build_opener(ah)
            urllib2.install_opener(opener)

        ph = urllib2.urlopen(stats_url)
        if ph is None:
            logging.warning('Could not fetch icecast2 stats.xml for some reason.')
            return -1

        r = self.stats_re.search(ph.read())
        if r is None:
            logging.warning('Could not find listener count in icecast2 stats.xml')
            return -1

        return int(r.group(1))


def Open(config):
    if not config.get('lastfm/enable', False):
        return None
    if not have_cli:
        logging.warning('Last.fm scrobbler is not available: please install lastfmsubmitd.')
        return None
    return client(config)
