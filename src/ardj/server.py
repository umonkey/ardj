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
        data = f(*args, **kwargs)

        if web.ctx.env["PATH_INFO"].endswith(".js"):
            var_name = "response"
            callback_name = None

            for part in web.ctx.env["QUERY_STRING"].split("&"):
                if part.startswith("var="):
                    var_name = part[4:]
                elif part.startswith("callback="):
                    callback_name = part[9:]

            if callback_name is not None:
                return "var %s = %s; %s(%s);" % (var_name, json.dumps(data), callback_name, var_name)
            return "var %s = %s;" % (var_name, json.dumps(data))
        else:
            return json.dumps(data, ensure_ascii=False, indent=True)
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

    def check_auth(self):
        """Makes sure the sender is allowed to use this privileged call."""
        remote_addr = web.ctx.env["REMOTE_ADDR"]

        trusted = settings.get("webapi_trusted_ips", ["127.0.0.1"])
        if remote_addr in trusted:
            return True

        tokens = settings.get("webapi_tokens", {})
        if remote_addr not in tokens:
            raise web.notfound("You don't have access to this call.")

        required_token = tokens.get(remote_addr)
        if required_token is None:
            return True

        current_token = web.ctx.env.get("HTTP_X_ARDJ_KEY", None)
        if current_token is None:
            raise web.forbidden("Your IP address is not in the trusted list, you must provide a valid auth token with the X-ARDJ-Key header.")

        if current_token != required_token:
            raise web.forbidden("Wrong auth token.")

        return True


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
    vote_value = 1

    @send_json
    def POST(self):
        try:
            self.check_auth()

            args = web.input(sender=None, track_id=None)
            track_id = args.track_id

            if not track_id or track_id == "None":
                track_id = tracks.get_last_track_id()

            weight = tracks.add_vote(track_id, args.sender, self.vote_value)
            if weight is None:
                message = 'No such track.'
            else:
                message = 'OK, current weight of track #%u is %.04f.' % (track_id, weight)

            return {"status": "ok", "message": message}
        except web.Forbidden:
            raise
        except Exception, e:
            logging.error("ERROR: %s\n%s" % (e, traceback.format_exc(e)))
            return {"status": "error", "message": str(e)}


class SucksController(RocksController):
    vote_value = -1


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
        "/api/status\.js(?:on)?", StatusController,
        "/api/track/rocks\.json", RocksController,
        "/api/track/sucks\.json", SucksController,
        "/commit\.json", CommitController,
        "/track/next\.json", NextController,
    )).run()


def run_cli(args):
    """Starts the HTTP web server on the configured socket."""
    serve_http(*settings.get("webapi_socket", "127.0.0.1:8080").split(":", 1))


__all__ = ["serve_http", "run_cli"]  # hide unnecessary internals
