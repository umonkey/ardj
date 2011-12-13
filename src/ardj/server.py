# encoding=utf-8

"""Web API for ardj.

Lets HTTP clients access the database.
"""

import logging
import sys
import threading
import time
import traceback

import json
import web

import database
import scrobbler
import settings
import tracks
import log


def send_json(f):
    """The @send_json decorator, encodes the return value in JSON."""
    def wrapper(*args, **kwargs):
        web.header("Content-Type", "text/plain; charset=UTF-8")
        return json.dumps(f(*args, **kwargs), ensure_ascii=False, indent=True)
    return wrapper


class ScrobblerThread(threading.Thread):
    """The scrobbler thread.  Waits for new data in the playlog table and
    submits it to Last.FM and Libre.FM."""
    def __init__(self, *args, **kwargs):
        self.lastfm = None
        self.librefm = None
        return threading.Thread.__init__(self, *args, **kwargs)

    def run(self):
        """The main worker."""
        logging.info("Scrobbler thread started.")
        while True:
            try:
                self.run_once()
            except Exception, e:
                log.log_error("Scrobbling failed: %s" % e, e)
            time.sleep(60)

    def run_once(self):
        """Submits all pending tracks and returns."""
        self.run_lastfm()
        self.run_librefm()

    def run_lastfm(self):
        if self.lastfm is None:
            self.lastfm = scrobbler.LastFM()
        self.lastfm.process()

    def run_librefm(self):
        if self.librefm is None:
            self.librefm = scrobbler.LibreFM()
        self.librefm.process()


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


class StatusController(Controller):
    @send_json
    def GET(self):
        track_id = tracks.get_last_track_id()
        if track_id is None:
            return None

        track = tracks.get_track_by_id(track_id)
        if track is None:
            return None

        return track


def serve_http(hostname, port):
    """Starts the HTTP web server at the specified socket."""
    sys.argv.insert(1, "%s:%s" % (hostname, port))

    logging.info("Starting the ardj web service at http://%s:%s/" % (hostname, port))

    ScrobblerThread().start()

    web.application((
        "/api/status\.json", StatusController,
        "/track/next\.json", NextController,
        "/track/rocks\.json", RocksController,
        "/commit\.json", CommitController,
    )).run()


def run_cli(args):
    """Starts the HTTP web server on the configured socket."""
    serve_http(*settings.get("webapi_socket", "127.0.0.1:8080").split(":", 1))


__all__ = ["serve_http", "run_cli"]  # hide unnecessary internals
