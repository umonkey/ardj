# vim: set fileencoding=utf-8:

import feedparser
import glob
import httplib2
import os
import time
import urlparse

import ardj.database
import ardj.log
import ardj.replaygain
import ardj.settings
import ardj.util
import ardj.website

def add_song(artist, title, mp3_link, tags):
    cur = ardj.database.Open().cursor()
    track_id = cur.execute('SELECT id FROM tracks WHERE artist = ? AND title = ?', (artist, title, )).fetchone()
    if track_id is None:
        ardj.log.info('Downloading "%s" by %s' % (title, artist))
        try:
            filename = ardj.util.fetch(mp3_link)
            ardj.add_file(str(filename), { 'artist': artist, 'title': title, 'labels': tags, 'owner': 'podcaster' })
            ardj.database.commit()
            return True
        except Exception, e:
            ardj.log.error('Could not fetch %s: %s' % (mp3_link, e))

def update_feeds():
    for podcast in ardj.settings.get('podcasts/feeds', []):
        ardj.log.info('Updating %s' % podcast['name'].encode('utf-8'))
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
                        pass # return # one at a time, for testing

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
                        if not author and 'author' in entry:
                            author = entry['author']
                        item = {
                            'author': author,
                            'date': entry['updated_parsed'],
                            'description': u'<p>Полное описание можно найти на <a href="%s">сайте автора</a>.</p>' % entry['link'],
                            'file': enclosure['href'],
                            'filesize': self.get_enclosure_size(enclosure, entry),
                            'tags': podcast['tags'],
                            'title': entry['title'],
                        }
                        if 'filename' in podcast:
                            item['filename'] = time.strftime(podcast['filename'], entry['updated_parsed'])
                        items.append(item)
        return items

    def get_enclosure_size(self, enclosure, entry):
        if 'length' in enclosure and enclosure['length'].isdigit():
            return int(enclosure['length'])
        return 0

    def process_entries(self, entries):
        rebuild = False
        post_dir = os.path.join(ardj.settings.getpath('website/root_dir'), ardj.settings.getpath('podcasts/site_post_dir'))
        for entry in entries:
            if entry['file'] not in self.known_urls:
                post_fn = self.get_new_episode_fn()
                self.upload_entry(entry)
                self.publish_entry(entry, post_fn)
                rebuild = True
        if rebuild:
            ardj.website.update('update-podcasts')

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
        ardj.log.info('Reposting %s' % os.path.basename(filename))
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
            ardj.log.error(str(e))

    def get_filesize(self, entry):
        if entry['filesize']:
            return entry['filesize']

        h = httplib2.Http()
        r = h.request(entry['file'], 'HEAD')[0]
        if r['status'] == '200':
            return int(r['content-length'])

        return 0

def run_cli(args):
    """CLI interface to the podcast module."""
    obj = Podcaster()
    obj.process_entries(obj.get_entries())
