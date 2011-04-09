# vim: set fileencoding=utf-8:

import feedparser
import httplib2
import os
import time
import urlparse

import ardj.database
import ardj.log
import ardj.settings
import ardj.util
import ardj.website

def fetch_file(url):
    filename = ardj.util.fetch(url, '.mp3')
    #normalizer = '/usr/lib/ardj/robots/normalizer'
    #if os.path.exists(normalizer):
    #    ardj.util.run(['/usr/lib/ardj/robots/normalizer', filename])
    return filename

def add_song(artist, title, mp3_link, tags):
    cur = ardj.database.Open().cursor()
    track_id = cur.execute('SELECT id FROM tracks WHERE artist = ? AND title = ?', (artist, title, )).fetchone()
    if track_id is None:
        ardj.log.info('Downloading "%s" by %s' % (title, artist))
        try:
            filename = fetch_file(mp3_link)
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
        pass

    def get_entries(self):
        """Returns a list of available episodes."""
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
            if 'filename' in entry:
                post_fn = os.path.join(post_dir, entry['filename'] + '.md')
                if not os.path.exists(post_fn):
                    self.upload_entry(entry)
                    self.publish_entry(entry, post_fn)
                    rebuild = True
        if rebuild:
            ardj.website.update('update-podcasts')

    def publish_entry(self, entry, filename):
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
        upath = urlparse.urlparse(ardj.settings.get('podcasts/file_upload'))
        src_filename = fetch_file(entry['file'])
        dst_filename = upath.path.rstrip('/') + '/' + entry['filename'] + '.mp3'

        if upath.scheme == 'sftp':
            target = upath.netloc + ':' + dst_filename
            ardj.util.run([ 'scp', '-q', src_filename, target ])
        else:
            ardj.log.error("Don't know how to upload to %s" % upath.scheme)

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
