# encoding=utf-8

import logging
import os
import os.path
import sys
import traceback

import mutagen
import mutagen.oggvorbis
import mutagen.mp3 as mp3
import mutagen.easyid3 as easyid3
from mutagen.apev2 import APEv2

from ardj.log import log_error

easyid3.EasyID3.RegisterTXXXKey('ardj', 'ardj')
easyid3.EasyID3.RegisterTXXXKey('ql:ardj', 'QuodLibet::ardj')


class FileNotFound(RuntimeError):
    pass


class UnsupportedFileType(RuntimeError):
    pass


def raw(filename):
    """
    Returns a mutagen object that corresponds to filename. The object can be
    used as a dictionary to access lists of tags, e.g.: t['title'][0]. Track
    length in seconds is t.info.length.
    """
    if not os.path.exists(filename):
        raise FileNotFound('File %s not found.' % filename)

    tmap = {'.mp3': mutagen.easyid3.Open, '.ogg': mutagen.oggvorbis.Open}

    extension = os.path.splitext(filename)[1].lower()
    if extension not in tmap:
        raise UnsupportedFileType('Unsupported file type: %s' % extension)

    handler = tmap[extension]

    try:
        return handler(filename)
    except:
        return handler()


class Wrapper(dict):
    def __init__(self, filename):
        self.filename = filename
        self.length = None
        self.read()

    def read(self):
        self.clear()
        ext = os.path.splitext(self.filename)[1].lower()
        if ext in ('.oga', '.ogg'):
            self.read_vorbis()
        elif ext in ('.mp3'):
            self.read_mp3()
        else:
            raise TypeError('File %s is of an unknown type.')
        self.parse_special()

    def parse_special(self):
        if 'ardj' in self and self['ardj'].startswith('ardj=1;'):
            for part in self['ardj'].split(';')[1:]:
                k, v = part.split('=', 1)
                self[k] = v
            del self['ardj']

        if 'labels' in self:
            self['labels'] = self['labels'].split(',')

    def read_vorbis(self):
        tags = mutagen.oggvorbis.Open(self.filename)
        for k, v in tags.items():
            self[k] = v[0]
        self['length'] = int(tags.info.length)
        self['sample_rate'] = tags.info.sample_rate
        self['channels'] = tags.info.channels

    def read_mp3(self):
        try:
            for k, v in APEv2(self.filename).items():
                self[k.lower()] = str(v)
        except:
            pass

        try:
            tags = mp3.Open(self.filename)
            for k, v in tags.items():
                if k == 'TPE1':
                    k, v = 'artist', v.text[0]
                elif k == 'TALB':
                    k, v = 'album', v.text[0]
                elif k == 'TIT2':
                    k, v = 'title', v.text[0]
                elif k == 'TRCK':
                    k, v = 'tracknumber', v.text[0]
                elif k.startswith('TXXX:'):
                    k, v = k[5:].lower(), v.text[0]
                elif k.startswith('COMM:'):
                    k, v = 'comment', v.text[0]
                else:
                    continue
                if k.startswith('quodlibet::'):
                    k = k[11:]
                self[k] = v
            self['length'] = int(tags.info.length)
            self['sample_rate'] = tags.info.sample_rate
        except:
            pass


def get(filename):
    return Wrapper(filename)


def set(filename, tags):
    try:
        t = raw(filename)
        for k, v in tags.items():
            if k not in ('length', 'length', 'sample_rate', 'channels', 'mp3gain_minmax', 'replaygain_track_peak', 'replaygain_track_gain'):
                if v is not None:
                    t[k] = v
        t.save(filename)
    except Exception, e:
        log_error("Could not save tags to %s: %s" % (filename, e), e)
