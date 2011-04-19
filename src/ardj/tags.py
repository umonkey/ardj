# encoding=utf-8

import os
import sys
import traceback

__all__ = ['get', 'set']

try:
    import mutagen
    import mutagen.oggvorbis
    import mutagen.mp3 as mp3
    import mutagen.easyid3 as easyid3
    from mutagen.apev2 import APEv2 
    easyid3.EasyID3.RegisterTXXXKey('ardj', 'ardj metadata')
except ImportError, e:
    print >>sys.stderr, 'Pleasy install python-mutagen (%s)' % e
    sys.exit(13)

import ardj.log


class FileNotFound(RuntimeError): pass

class UnsupportedFileType(RuntimeError): pass


def raw(filename):
    """
    Returns a mutagen object that corresponds to filename. The object can be
    used as a dictionary to access lists of tags, e.g.: t['title'][0]. Track
    length in seconds is t.info.length.
    """
    if not os.path.exists(filename):
        raise FileNotFound('File %s not found.' % filename)

    tmap = { '.mp3': mutagen.easyid3.Open, '.ogg': mutagen.oggvorbis.Open }

    extension = os.path.splitext(filename)[1].lower()
    if extension not in tmap:
        raise UnsupportedFileType('Unsupported file type: %s' % extension)

    handler = tmap[extension]

    try:
        return handler(filename)
    except:
        return handler()


def get(filename):
    t = raw(filename)
    result = dict([(k, type(v) == list and v[0] or v) for k, v in t.items()])
    result['length'] = int(mutagen.File(filename).info.length)

    if 'ardj' in result:
        for part in result['ardj'].split(';'):
            if part.startswith('ardj=') and part != 'ardj=1':
                ardj.log.warning('%s in %s' % (part, filename))
                break
            elif '=' in part:
                k, v = part.split('=', 1)
                if k == 'labels':
                    result['labels'] = v.split(',')

    return result

def set(filename, tags):
    try:
        t = raw(filename)
        for k, v in tags.items():
            if k not in ('length'):
                if v is not None:
                    t[k] = v
        t.save(filename)
    except Exception, e:
        print filename
        ardj.log.error(u'Could not save tags to %s: %s' % (filename, e) + traceback.format_exc(e))
