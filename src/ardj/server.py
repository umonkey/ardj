# encoding=utf-8

"""Web API for ardj.

Lets HTTP clients access the database.
"""

import logging
import sys

import json
import web

import tracks


def send_json(f):
    """The @send_json decorator, encodes the return value in JSON."""
    def wrapper(*args, **kwargs):
        web.header("Content-Type", "text/plain; charset=UTF-8")
        return json.dumps(f(*args, **kwargs), ensure_ascii=False, indent=True)
    return wrapper


class NextController:
    """Handles the /track/next.json request by returning a JSON description of
    the track that should be played next.  Only responds to POST requests to
    prevent accidential access."""
    @send_json
    def POST(self):
        track_id = tracks.get_next_track_id()
        if not track_id:
            logging.error("Could not satisfy a request -- no tracks.")
            raise web.internalerror("No data.")

        track = tracks.get_track_by_id(track_id)
        if track is None:
            logging.error("Could not satisfy a request -- track %s is unknown." % track_id)
            raise web.internalerror("Could not pick a track.")

        return track


def serve_http(hostname, port):
    """Starts the HTTP web server at the specified socket."""
    del sys.argv[1:]
    sys.argv.extend([hostname, port])

    web.application((
        "/track/next\.json", NextController,
    )).run()


def run_cli(args):
    """Starts the HTTP web server on the configured socket."""
    serve_http("127.0.0.1", "8080")


__all__ = ["serve_http", "run_cli"]  # hide unnecessary internals
