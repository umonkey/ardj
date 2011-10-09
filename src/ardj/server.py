# encoding=utf-8

"""Web API for ardj.

Lets HTTP clients access the database.
"""

import logging
import sys
import traceback

import json
import web

import database
import scrobbler
import tracks


def send_json(f):
    """The @send_json decorator, encodes the return value in JSON."""
    def wrapper(*args, **kwargs):
        web.header("Content-Type", "text/plain; charset=UTF-8")
        return json.dumps(f(*args, **kwargs), ensure_ascii=False, indent=True)
    return wrapper


class Controller:
    def __init__(self):
        logging.debug("Request: %s" % web.ctx.path)

    def __del__(self):
        logging.debug("Request finished, closing the transaction.")
        database.commit()


class NextController(Controller):
    """Handles the /track/next.json request by returning a JSON description of
    the track that should be played next.  Only responds to POST requests to
    prevent accidential access."""
    @send_json
    def POST(self):
        try:
            track = tracks.get_next_track()
            if track is None:
                raise web.internalerror("No data.")
            logging.debug("Returning track info: %s" % track)
            return track
        except Exception, e:
            logging.error("Error handling a request: %s\n%s" % (e, traceback.format_exc(e)))
            return {"status": "error", "message": str(e)}


class ScrobbleController(Controller):
    """Sends scheduled tracks to Last.fm and Libre.fm."""
    def __init__(self):
        self.lastfm = scrobbler.LastFM()
        self.librefm = ardj.scrobbler.LibreFM()

    def POST(self):
        return
        """
        commit = False
        if self.lastfm:
            try:
                if self.lastfm.process():
                    commit = True
            except Exception, e:
                logging.error('Could not process LastFM queue: %s' % e)

        if self.librefm:
            try:
                if self.librefm.process():
                    commit = True
            except Exception, e:
                logging.error('Could not process LibreFM queue: %s' % e)

        if commit:
            ardj.database.commit()
        """


class CommitController(Controller):
    @send_json
    def POST(self):
        database.commit()
        return {"status": "ok"}


class RocksController(Controller):
    @send_json
    def POST(self):
        try:
            args = web.input(sender=None, track_id=None)

            track_id = args.track_id
            if not track_id or track_id == "None":
                track_id = tracks.get_last_track_id()

            weight = tracks.add_vote(track_id, args.sender, 1)
            if weight is None:
                message = 'No such track.'
            else:
                message = 'OK, current weight of track #%u is %.04f.' % (track_id, weight)

            return {"status": "ok", "message": message}
        except Exception, e:
            logging.error("ERROR: %s\n%s" % (e, traceback.format_exc(e)))
            return {"status": "error", "message": str(e)}


def serve_http(hostname, port):
    """Starts the HTTP web server at the specified socket."""
    del sys.argv[1:]
    sys.argv.extend([hostname, port])

    logging.info("Starting the ardj web service at http://%s:%s/" % (hostname, port))

    web.application((
        "/track/next\.json", NextController,
        "/track/rocks\.json", RocksController,
        "/scrobble\.json", ScrobbleController,
        "/commit\.json", CommitController,
    )).run()


def run_cli(args):
    """Starts the HTTP web server on the configured socket."""
    serve_http("127.0.0.1", "8080")


__all__ = ["serve_http", "run_cli"]  # hide unnecessary internals
