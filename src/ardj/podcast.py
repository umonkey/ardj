# vim: set fileencoding=utf-8:

import glob
import logging
import os
import time
import urllib
import urlparse

try:
    import feedparser
except ImportError:
    pass

try:
    import httplib2
except ImportError:
    pass

import ardj.database
import ardj.replaygain
import ardj.settings
import ardj.tracks
import ardj.util
import ardj.website


def add_song(artist, title, mp3_link, tags):
    """Adds a song to the database.

    Does nothing if the song is already in the database (only artist/title are
    checked).  TODO: check duration and file size also."""
    track_id = ardj.database.fetchone('SELECT id FROM tracks WHERE artist = ? AND title = ?', (artist, title, ))
    if track_id is None:
        logging.info((u'Downloading "%s" by %s' % (title, artist)).encode("utf-8"))
        try:
            filename = ardj.util.fetch(mp3_link)
            ardj.add_file(str(filename), {'artist': artist, 'title': title, 'labels': tags, 'owner': 'podcaster'})
            ardj.database.commit()
            return True
        except Exception, e:
            logging.error('Could not fetch %s: %s' % (mp3_link, e))


def update_feeds():
    """Updates all feeds.

    Scans all feeds described in podcasts/feeds, then calls add_song() for each
    episode."""
    for podcast in ardj.settings.get('podcasts/feeds', []):
        logging.info('Updating %s' % podcast['name'].encode('utf-8'))
        feed = feedparser.parse(podcast['feed'])

        feed_author = None
        if 'author' in podcast:
            feed_author = podcast['author']

        for entry in feed['entries']:
            if 'enclosures' in entry:
                for enclosure in entry['enclosures']:
                    author = feed_author
                    if not author and 'author' in entry:
                        author = entry['author']
                    if add_song(author, entry['title'], enclosure['href'], podcast['tags']):
                        pass  # return # one at a time, for testing


class Podcaster:
    def __init__(self):
        self.last_episode = 0
        self.known_urls = self.get_known_urls()

    def get_known_urls(self):
        """Returns a list of URLs of local episodes.

        Local episodes are those that have a page on the local web site.  This
        is used to avoid duplicates."""
        result = []
        wdir = ardj.settings.getpath('website/root_dir')
        ldir = ardj.settings.getpath('podcasts/site_post_dir')
        if wdir and ldir:
            expr = os.path.join(wdir, ldir, '*', 'index.md')
            for filename in glob.glob(expr):
                self.last_episode = max(self.last_episode, int(filename.split(os.path.sep)[-2]))
                page = ardj.website.load_page(filename)
                if 'file' in page:
                    result.append(page['file'])
        return result

    def get_entries(self):
        """Returns a list of all available episodes."""
        items = []
        for podcast in ardj.settings.get('podcasts/feeds', []):
            feed = feedparser.parse(podcast['feed'])

            feed_author = None
            if 'author' in podcast:
                feed_author = podcast['author']

            for entry in feed['entries']:
                if 'enclosures' in entry:
                    for enclosure in entry['enclosures']:
                        author = feed_author

                        if entry.get('guid', '').startswith('http://alpha.libre.fm/'):
                            parts = entry['guid'].split('/')
                            if parts[3] == 'artist':
                                entry['author'] = urllib.unquote_plus(parts[4])
                            if parts[3] == 'track':
                                entry['title'] = urllib.unquote_plus(parts[8])

                        if not author and 'author' in entry:
                            author = entry['author']

                        item = {
                            'author': author,
                            'date': entry.get('updated_parsed'),
                            'description': u'Описание отсутствует.',
                            'file': enclosure.get('href'),
                            'filesize': self.get_enclosure_size(enclosure, entry),
                            'tags': podcast.get('tags', []),
                            'title': entry.get('title', 'Заголовок отсутствует'),
                            'repost': podcast.get('repost'),
                            'add_to_db': podcast.get('add_to_db', True),
                        }

                        if 'link' in entry:
                            item['description'] = u'<p>Полное описание можно найти на <a href="%s">сайте автора</a>.</p>' % entry['link']
                        if 'filename' in podcast:
                            item['filename'] = time.strftime(podcast['filename'], entry['updated_parsed'])
                        items.append(item)
        return items

    def get_enclosure_size(self, enclosure, entry):
        if 'length' in enclosure and enclosure['length'].isdigit():
            return int(enclosure['length'])
        return 0

    def process_entries(self, entries):
        """Adds entries to the database."""
        added = 0
        for entry in entries:
            if entry['add_to_db']:
                logging.info((u'[%u/%u] adding "%s" by %s' % (added + 1, len(entries), entry['title'], entry['author'])).encode("utf-8"))
                fn = ardj.util.fetch(entry['file'])
                ardj.tracks.add_file(str(fn), add_labels=entry['tags'], quiet=True)
                added += 1
            """
            if entry['file'] not in self.known_urls:
                post_fn = self.get_new_episode_fn()
                self.upload_entry(entry)
                if entry.get('filename'):
                    self.publish_entry(entry, post_fn)
                rebuild = True
            """

        if added:
            ardj.jabber.chat_say('Added %u tracks from podcasts.' % added)

    def get_new_episode_fn(self):
        """Prepares a file for a new episode.

        Returns the name of the file.  Creates directories if needed."""
        post_dir = os.path.join(ardj.settings.getpath('website/root_dir'), ardj.settings.getpath('podcasts/site_post_dir'))

        while True:
            edir = os.path.join(post_dir, str(self.last_episode + 1))
            self.last_episode += 1
            if not os.path.exists(edir):
                os.mkdir(edir)
                return os.path.join(edir, 'index.md')

    def publish_entry(self, entry, filename):
        """Adds a page for the episode.

        Creates the source file for the page (index.md); to actually create the
        web page, ardj.website.update() must be called.

        TODO: use ardj.website.add_page()."""
        e = entry
        logging.info('Reposting %s' % os.path.basename(filename))
        if not entry.get('filename'):
            print entry
        else:
            e['file_backup'] = ardj.settings.get('podcasts/file_base').rstrip('/') + '/' + entry['filename'] + '.mp3'
            e['labels'] = u', '.join(entry['tags'])
            e['date_time'] = time.strftime('%Y-%m-%d %H:%M', entry['date'])
            e['filesize'] = self.get_filesize(entry)
            text = u'title: %(title)s\nauthor: %(author)s\nfile: %(file)s\nfile_backup: %(file_backup)s\nfilesize: %(filesize)u\nlabels: %(labels)s\ndate: %(date_time)s\n---\n%(description)s' % e

            f = open(filename, 'wb')
            f.write(text.encode('utf-8'))
            f.close()

    def upload_entry(self, entry):
        try:
            ardj.util.upload(ardj.util.fetch(entry['file']), ardj.settings.get('podcasts/file_upload'))
        except Exception, e:
            logging.error(str(e))

    def get_filesize(self, entry):
        if entry['filesize']:
            return entry['filesize']

        h = httplib2.Http()
        r = h.request(entry['file'], 'HEAD')[0]
        if r['status'] == '200':
            return int(r['content-length'])

        return 0


def find_new_tracks(artist_names=None):
    """Returns a list of available podcast episodes."""
    obj = Podcaster()

    result = []
    for entry in obj.get_entries():
        if not entry['add_to_db']:
            continue
        if artist_names:
            if not ardj.util.in_list(entry['author'] or '', artist_names):
                continue
        result.append({
            'artist': entry['author'],
            'title': entry['title'],
            'url': entry['file'],
            'tags': entry['tags'],
        })
    return result


def run_cli(args):
    """CLI interface to the podcast module."""
    obj = Podcaster()
    entries = obj.get_entries()
    obj.process_entries(entries)
