import os
import sys
import traceback

import ardj.log
import ardj.replaygain
import ardj.settings
import ardj.tags
import ardj.tracks
import ardj.util

DEFAULT_URL = 'http://broadcast.echo.msk.ru:9000/content/current.mp3'


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
        ardj.log.error('Could not transcode %s' % src)
        return False

    ardj.replaygain.update(str(tmp))

    if os.path.exists(dst):
        os.unlink(dst)
    ardj.util.move_file(str(tmp), dst)

    tags = ardj.tags.get(dst)
    tags['source_md5'] = src_md5
    ardj.tags.set(dst, tags)

    return tags.get('length')


def fetch_news():
    track_id = ardj.settings.get('news/track_id', fail=True)
    track_filename = ardj.tracks.get_track_by_id(track_id)['filepath']
    if not track_filename.endswith('.ogg'):
        raise Exception('Track %u is not OGG/Vorbis.' % track_id)
    track_length = 0

    source_fn = ardj.util.fetch(ardj.settings.get('news/url', DEFAULT_URL))
    track_length = transcode(str(source_fn), track_filename)
    if track_length > 0:
        ardj.database.cursor().execute('UPDATE tracks SET length = ?, count = 0 WHERE id = ?', (track_length, track_id, ))
        if ardj.settings.get('news/queue') == 'yes':
            ardj.tracks.queue(track_id)
        ardj.database.Open().commit()

    return track_length != 0


def update(args):
    """Updates the news from echo.msk.ru"""
    fetch_news()
