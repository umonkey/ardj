import logging
import logging.handlers
import sys

import ardj.settings


class Logger:
    instance = None

    def __init__(self):
        self.log = logging.getLogger('ardj')
        self.log.setLevel(logging.DEBUG)

        h = logging.handlers.RotatingFileHandler(ardj.settings.getpath('log', '~/ardj.log'), maxBytes=1000000, backupCount=5)
        h.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        h.setLevel(logging.DEBUG)
        self.log.addHandler(h)

    @classmethod
    def get(cls):
        if cls.instance is None:
            cls.instance = cls()
        return cls.instance

def debug(text, quiet=False):
    if not quiet:
        try: print >>sys.stderr, text.strip().encode('utf-8')
        except: pass
    Logger.get().log.debug(text)

def info(text, quiet=False):
    if not quiet:
        try: print >>sys.stderr, text.strip().encode('utf-8')
        except: pass
    Logger.get().log.info(text)

def warning(text, quiet=False):
    if not quiet:
        try: print >>sys.stderr, text.strip().encode('utf-8')
        except: pass
    Logger.get().log.warning(text)

def error(text, quiet=False):
    if not quiet:
        try: print >>sys.stderr, text.strip().encode('utf-8')
        except: pass
    Logger.get().log.error(text)
