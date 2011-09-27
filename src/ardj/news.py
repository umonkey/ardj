import logging
import os
import re
import sys
import traceback

import ardj.replaygain
import ardj.settings
import ardj.tags
import ardj.tracks
import ardj.util


class MayakNews:
    PLAYLIST_URL = 'http://www.radiomayak.ru/player_list.html?mode=0'
    FILE_URL_BASE = 'http://www.radiomayak.ru/a/%u.asf'

    def get_episode_urls(self):
        page = self.fetch(self.PLAYLIST_URL)
        if page is None:
            return []
        r = re.findall('&aid=(\d+)', page)
        ids = sorted(list(set(r)), key=lambda x: int(x), reverse=True)
        return [self.FILE_URL_BASE % int(id) for id in ids]

    def get_last_episode_url(self):
        urls = self.get_episode_urls()
        if urls:
            return urls[0]

    def fetch(self, url):
        return ardj.util.fetch(url, quiet=True, ret=True)


def transcode(src, dst):
    """Transcodes the file if necessary.

    Transcoding is performed if the destination file does not exist or if the
    value stored in its "source_md5" tag differs from the MD5 sum of the source
    file.

    Returns False if the transcoding was not performed, track length in seconds
    otherwise.
    """

    src_md5 = ardj.util.filemd5(src)

    if os.path.exists(dst):
        tags = ardj.tags.get(dst)
        dst_md5 = ardj.tags.get(dst).get('source_md5', 'no_md5')
        if dst_md5 == src_md5:
            print 'No news.'
            return False
        print '%s != %s' % (src_md5, dst_md5)

    tmp = ardj.util.mktemp(suffix='.ogg')
    ardj.util.run([ 'ffmpeg', '-y', '-i', src, '-ar', '44100', '-ac', '2', '-acodec', 'vorbis', str(tmp) ], quiet=True)
    if not os.stat(str(tmp)).st_size:
        logging.error('Could not transcode %s' % src)
        return False

    ardj.replaygain.update(str(tmp))

    if os.path.exists(dst):
        os.unlink(dst)
    ardj.util.move_file(str(tmp), dst)

    tags = ardj.tags.get(dst)
    tags['source_md5'] = src_md5
    ardj.tags.set(dst, tags)

    return tags.get('length')


def fetch_news(url, track_id):
    track_filename = ardj.tracks.get_track_by_id(track_id)['filepath']
    if not track_filename.endswith('.ogg'):
        raise Exception('Track %u is not OGG/Vorbis.' % track_id)
    track_length = 0

    source_fn = ardj.util.fetch(url)
    if source_fn is None:
        return False

    track_length = transcode(str(source_fn), track_filename)
    if track_length > 0:
        ardj.database.cursor().execute('UPDATE tracks SET length = ?, count = 0 WHERE id = ?', (track_length, track_id, ))
        if ardj.settings.get('news/queue') == 'yes':
            ardj.tracks.queue(track_id)
        ardj.database.Open().commit()

    return track_length != 0


def update_source(source):
    url = source.get('url')
    track_id = source.get('track_id')

    if url == 'mayak':
        url = MayakNews().get_last_episode_url()

    if url and track_id:
        fetch_news(url, track_id)


def update_all_sources():
    for source in ardj.settings.get('news/sources', []):
        update_source(source)


def run_cli(args):
    """Updates the news from echo.msk.ru"""
    update_all_sources()
