# vim: set fileencoding=utf-8:

import logging
import email.utils
import os
import sys
import time

import mutagen

import ardj.settings
import ardj.twitter

USAGE = """Usage: ardj stream start"""


def twit_file(filename, silent=False):
    dur = get_air_duration(filename)
    if dur < ardj.settings.get('stream/twit_duration_min', 10):
        return
    twit = time.strftime(ardj.settings.get('stream/twit_end').encode('utf-8')).decode('utf-8')
    twit = twit.replace('URL', ardj.settings.get('stream/base_url') + os.path.basename(filename))
    twit = twit.replace('LENGTH', str(dur))

    if not silent:
        ardj.twitter.send_message(twit)


def start_stream():
    src = ardj.settings.getpath('stream/dump', fail=True)
    dst = time.strftime(ardj.settings.getpath('stream/dump_rename_to', fail=True))

    if not os.path.exists(src):
        logging.error('False start: %s not found.' % src)
        return False

    os.rename(src, dst)
    ardj.twitter.send_message(ardj.settings.get('stream/twit_begin', 'Somebody is on air!'))
    return True


def run_cli(args):
    """Implements the "ardj stream" command."""
    if len(args) and args[0] == 'start':
        return start_stream()
    print USAGE
