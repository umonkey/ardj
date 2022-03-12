"""
Hooks for the ices0 source.
"""

# encoding=utf-8

import logging
import os

from ardj.log import install as init_logging
from ardj.tracks import get_track_to_play_next


SONG_NUMBER = -1
LAST_TRACK = None
LAST_GOOD_FILE = None


def ices_init():
    """
    Function called to initialize your Python environment.
    Should return 1 if ok, and 0 if something went wrong.
    """
    init_logging("ardj-ices")
    logging.info('Initializing.')
    return 1


def ices_shutdown():
    """
    Function called to shutdown your Python enviroment.
    Return 1 if ok, 0 if something went wrong.
    """
    logging.info('Shutting down.')
    return 1


def ices_get_next():
    """
    Function called to get the next filename to stream.
    Should return a string.
    """
    global LAST_TRACK, LAST_GOOD_FILE

    LAST_TRACK = get_track_to_play_next()

    if LAST_TRACK and os.path.exists(LAST_TRACK["filepath"]):
        LAST_GOOD_FILE = LAST_TRACK["filepath"].encode("utf-8")
    elif LAST_GOOD_FILE:
        logging.warning("Replaying last good file due to an error.")

    return LAST_GOOD_FILE


def ices_get_metadata():
    """
    This function, if defined, returns the string you'd like used
    as metadata (ie for title streaming) for the current song. You may
    return null to indicate that the file comment should be used.
    """
    global LAST_TRACK
    if LAST_TRACK:
        if "artist" in LAST_TRACK and "title" in LAST_TRACK:
            return ("\"%s\" by %s" %
                    (LAST_TRACK["title"], LAST_TRACK["artist"])).encode("utf-8")
        return os.path.basename(LAST_TRACK["filepath"])
    return "Unknown track"


def ices_get_lineno():
    """
    Function used to put the current line number of
    the playlist in the cue file. If you don't care about this number
    don't use it.
    """
    global SONG_NUMBER
    SONG_NUMBER = SONG_NUMBER + 1
    return SONG_NUMBER
