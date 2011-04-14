# vim: set fileencoding=utf-8:

import os
import sys
import time

import ardj.log
import ardj.settings
import ardj.twitter

USAGE = """Usage: ardj stream start|stop"""


def start_stream():
    src = ardj.settings.getpath('stream/dump', fail=True)
    dst = time.strftime(ardj.settings.getpath('stream/dump_rename_to', fail=True))

    if not os.path.exists(src):
        ardj.log.error('False start: %s not found.' % src)
        return False

    os.rename(src, dst)
    ardj.twitter.twit(ardj.settings.get('stream/twit_begin', 'Somebody is on air!'))
    return True


def run_cli(args):
    """Implements the "ardj stream" command."""
    if len(args) and args[0] == 'start':
        return start_stream()
    if len(args) and args[0] == 'stop':
        return stop_stream()
    print USAGE
