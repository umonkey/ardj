# encoding=utf-8

import logging
import os

from ardj.log import install as init_logging
from ardj.tracks import get_track_to_play_next


songnumber = -1
last_track = None
last_good_file = None


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
    global last_track, last_good_file

    last_track = get_track_to_play_next()

    if last_track and os.path.exists(last_track["filepath"]):
        last_good_file = last_track["filepath"].encode("utf-8")
    elif last_good_file:
        logging.warning("Replaying last good file due to an error.")

    return last_good_file


def ices_get_metadata():
    """
    This function, if defined, returns the string you'd like used
    as metadata (ie for title streaming) for the current song. You may
    return null to indicate that the file comment should be used.
    """
    global last_track
    if last_track:
        if "artist" in last_track and "title" in last_track:
            return ("\"%s\" by %s" % (last_track["title"], last_track["artist"])).encode("utf-8")
        return os.path.basename(last_track["filepath"])
    return "Unknown track"


def ices_get_lineno():
    """
    Function used to put the current line number of
    the playlist in the cue file. If you don't care about this number
    don't use it.
    """
    global songnumber
    songnumber = songnumber + 1
    return songnumber
