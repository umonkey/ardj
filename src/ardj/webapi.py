# encoding=utf-8

"""Web API interface for ardj.

This module acts like ardj.api, but sends requests to the Web API server, which
lets other modules transparently use remote database or force single database
client (saves SQLite)."""


from ardj.util import fetch_json


def call_remote(method, **kwargs):
    """Performs a remote method call using a POST HTTP request."""
    data = fetch_json("http://127.0.0.1:8080" + method, args=kwargs, post=True, ret=True)
    if "error" in data:
        raise Exception(data["error"])
    return data


def get_next_track():
    """Returns a dictionary which describes the next track that must be played next."""
    return call_remote("/track/next.json")
