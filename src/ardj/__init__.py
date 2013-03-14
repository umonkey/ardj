#!/usr/bin/env python
# encoding=utf-8

"""ARDJ, an artificial DJ.

This software lets you automate an internet radio station.  Its purpose is to
maintain a database of audio files with metadata, feed ezstream with random
those files based on playlists, let listeners vote for music using an XMPP
client.

To interact with the software you use the `ardj' binary, which simply imports
the `ardj.cli' module and calls the run() method.  Look there to understand how
things work.
"""

import sys


def is_verbose():
    return "-v" in sys.argv


def is_dry_run():
    return "-n" in sys.argv
