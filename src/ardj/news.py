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

def fetch_news():
    track_id = ardj.settings.get('news/track_id', fail=True)
    track_filename = ardj.tracks.get_track_by_id(track_id)['filepath']
    if not track_filename.endswith('.ogg'):
        raise Exception('Track %u is not OGG/Vorbis.' % track_id)
    track_length = 0

    source_fn = ardj.util.fetch(ardj.settings.get('news/url', DEFAULT_URL))
    output_fn = ardj.util.mktemp(suffix='.ogg')

    try:
        ardj.util.run([ 'ffmpeg', '-y', '-i', str(source_fn), '-ar', '44100', '-ac', '2', '-acodec', 'vorbis', str(output_fn) ], quiet=True)
        if os.stat(str(output_fn)).st_size:
            ardj.replaygain.update(output_fn)

            if os.path.exists(track_filename):
                os.unlink(track_filename)
            os.chmod(str(output_fn), 0664)
            ardj.util.move_file(output_fn, track_filename)

            tags = ardj.tags.raw(track_filename)
            if tags:
                track_length = int(tags.info.length)
    except Exception, e:
        ardj.log.error('Could not update news: %s' % e)
        ardj.log.error(traceback.format_exc(e))

    ardj.database.cursor().execute('UPDATE tracks SET length = ?, count = 0 WHERE id = ?', (track_length, track_id, ))
    if ardj.settings.get('news/queue') == 'yes':
        ardj.tracks.queue(track_id)
    ardj.database.Open().commit()

    return track_length != 0


def update(args):
    """Updates the news from echo.msk.ru"""
    fetch_news()
