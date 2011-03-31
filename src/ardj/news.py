import os
import shutil
import sys
import traceback

import ardj
import ardj.settings
import ardj.tags
import ardj.util

DEFAULT_URL = 'http://broadcast.echo.msk.ru:9000/content/current.mp3'
DEFAULT_OUT = '/tmp/ardj-news.ogg'

def fetch_news():
    track_length = 0
    output_fn = ardj.util.mktemp(suffix='.ogg')
    cmd = u"gst-launch-0.10 -q souphttpsrc location=\"%s\" ! decodebin ! audioconvert ! vorbisenc quality=0.5 ! oggmux ! filesink location=\"%s\"" % (ardj.settings.get('news/url', DEFAULT_URL), output_fn)

    try:
        ardj.util.run(cmd.split(' '))
        if os.stat(str(output_fn)).st_size:
            ardj.util.run(['vorbisgain', '-f', '-q', output_fn])

            target_fn = ardj.settings.getpath('news/out', DEFAULT_OUT)
            if os.path.exists(target_fn):
                os.unlink(target_fn)
            os.chmod(str(output_fn), 0664)
            shutil.move(str(output_fn), target_fn)

            tags = ardj.tags.raw(target_fn)
            if tags:
                track_length = int(tags.info.length)
    except Exception, e:
        print >>sys.stderr, 'Could not fetch news: %s' % e
        traceback.print_exc(e)

    track_id = int(ardj.settings.get('news/track_id', '0'))
    if track_id:
        a = ardj.Open()
        a.database.cursor().execute('UPDATE tracks SET length = ? WHERE id = ?', (track_length, track_id, ))
        a.queue_track(track_id)
        if ardj.settings.get('queue') == 'yes':
            a.queue_track(track_id)
        a.database.commit()

    return track_length != 0


def update(args):
    """Updates the news from echo.msk.ru"""
    fetch_news()
