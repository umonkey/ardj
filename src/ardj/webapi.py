# encoding=utf-8

"""Web API interface for ardj.

This module acts like ardj.api, but sends requests to the Web API server, which
lets other modules transparently use remote database or force single database
client (saves SQLite)."""


import logging
import time

from ardj import settings
from ardj.util import fetch_json


def call_remote(method, **kwargs):
    """Performs a remote method call using a POST HTTP request."""
    _ts = time.time()
    try:
        socket = settings.get("webapi_socket", "127.0.0.1:8080")
        data = fetch_json("http://" + socket + method, args=kwargs, post=True, ret=True)
        if data is None:
            raise Exception("Could not query the web service.")
        if "error" in data:
            raise Exception(data["error"])
        return data
    finally:
        logging.debug("webapi.call(%s) took %s seconds." % (method, time.time() - _ts))


def get_next_track():
    """Returns a dictionary which describes the next track that must be played next."""
    return call_remote("/track/next.json")


def rocks(sender, track_id=None):
    return call_remote("/api/track/rocks.json", sender=sender, track_id=track_id)


def sucks(sender, track_id=None):
    return call_remote("/api/track/sucks.json", sender=sender, track_id=track_id)
