# vim: set fileencoding=utf-8:

"""Speech synthesizer.

Uses festival to render text."""

import logging
import os
import sys

import ardj.database
import ardj.settings
import ardj.tags
import ardj.util


def render_text_file(filename, artist=None, title=None):
    """Renders a text file to OGG/Vorbis.

    Returns output file name and duration in seconds."""

    for exe in ("text2wave", "sox", "oggenc"):
        if not ardj.util.is_command(exe):
            raise Exception("Speech synthesis is not available because the '%s' program is not installed." % exe)

    voice = ardj.settings.get('festival_voice', 'voice_msu_ru_nsh_clunits')

    output_wav = ardj.util.mktemp(suffix='.wav')
    ardj.util.run(['text2wave', '-f', '44100', '-eval', '(' + voice + ')', filename, '-o', output_wav])

    resampled_wav = ardj.util.mktemp(suffix='.wav')
    ardj.util.run(['sox', output_wav, '-r', '44100', '-c', '2', resampled_wav, 'pad', '2', '5'])

    output_ogg = ardj.util.mktemp(suffix='.ogg')
    ardj.util.run(['oggenc', '-Q', '-q', '9', '-o', output_ogg, '-a', 'artist', resampled_wav])

    ardj.util.run(['vorbisgain', '-q', output_ogg])

    tags = ardj.tags.raw(str(output_ogg))
    if tags is None:
        return output_ogg, 0

    tags['comment'] = open(str(filename), 'rb').read().decode('utf-8')
    tags['artist'] = artist or ardj.settings.get('speech/default_artist', 'Festival')
    tags['title'] = title or ardj.settings.get('speech/default_title', 'Text message')
    tags.save()

    return output_ogg, int(tags.info.length)


def render_text(text, artist=None, title=None, play=False):
    """Renders text to OGG/Vorbis.

    Writes text to a temporary file then renders it with render_text_file()."""
    filename = ardj.util.mktemp(suffix='.txt')
    if type(text) == unicode:
        text = text.encode('utf-8')
    open(str(filename), 'wb').write(text.strip())
    logging.info('Rendering text: %s' % text)
    filename, length = render_text_file(filename, artist, title)
    if play and length:
        ardj.util.run(['play', str(filename)])
    return filename, length


def render_and_queue(message):
    """Renders the text and queues it for playing.

    Returns an error message or None.
    """
    track_id = int(ardj.settings.get('festival_track_id', '0'))
    if not track_id:
        return "Эта функция отключена."

    rows = len(ardj.database.fetch('SELECT 1 FROM queue WHERE track_id = ?', (track_id, )))
    if rows:
        return 'All the circuits are busy.  Please retry in a few minutes.'

    rows = ardj.database.fetch('SELECT filename FROM tracks WHERE id = ?', (track_id, ))
    if not len(rows):
        return 'Track %u not found.' % track_id

    filename = rows[0][0]
    if not filename.endswith('.ogg'):
        return 'Track %u is not OGG/Vorbis.' % track_id

    tmpname, duration = render_text(message)
    ardj.util.move_file(tmpname, os.path.join(ardj.settings.get_music_dir(), filename))
    ardj.database.execute('UPDATE tracks SET length = ? WHERE id = ?', (duration, track_id, ))
    ardj.database.execute('INSERT INTO queue (track_id, owner) VALUES (?, ?)', (track_id, 'ardj', ))


def render_text_cli(args):
    """Renders text to voice using festival and plays it."""
    if not args:
        print 'Usage: ardj say message [artist [title]]'
        return 1
    args.append('Some Artist')
    args.append('Some Title')
    filename, length = render_text(args[0], args[1], args[2], play=True)
