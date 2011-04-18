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

    output_fn = ardj.util.mktemp(suffix='.ogg')
    cmd = u"gst-launch-0.10 -q souphttpsrc location=\"%s\" ! decodebin ! audioconvert ! vorbisenc quality=0.5 ! oggmux ! filesink location=\"%s\"" % (ardj.settings.get('news/url', DEFAULT_URL), output_fn)

    try:
        ardj.util.run(cmd.split(' '))
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
        ardj.log.error('Could not fetch news: %s' % e)
        ardj.log.error(traceback.format_exc(e))

    ardj.database.cursor().execute('UPDATE tracks SET length = ? WHERE id = ?', (track_length, track_id, ))
    if ardj.settings.get('news/queue') == 'yes':
        ardj.tracks.queue(track_id)
    ardj.database.Open().commit()

    return track_length != 0


def update(args):
    """Updates the news from echo.msk.ru"""
    fetch_news()
