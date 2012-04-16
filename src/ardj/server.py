# encoding=utf-8

"""Web API for ardj.

Lets HTTP clients access the database.
"""

import logging
import os
import sys
import threading
import time
import traceback

import json
import web

import auth
import console
import database
import scrobbler
import settings
import tracks
import log


def send_json(f):
    """The @send_json decorator, encodes the return value in JSON."""
    def wrapper(*args, **kwargs):
        web.header("Access-Control-Allow-Origin", "*")
        data = f(*args, **kwargs)

        if web.ctx.env["PATH_INFO"].endswith(".js"):
            var_name = "response"
            callback_name = None

            for part in web.ctx.env["QUERY_STRING"].split("&"):
                if part.startswith("var="):
                    var_name = part[4:]
                elif part.startswith("callback="):
                    callback_name = part[9:]

            web.header("Content-Type", "application/javascript; charset=UTF-8")
            if callback_name is not None:
                return "var %s = %s; %s(%s);" % (var_name, json.dumps(data), callback_name, var_name)
            return "var %s = %s;" % (var_name, json.dumps(data))
        else:
            web.header("Content-Type", "application/json; charset=UTF-8")
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
        logging.debug("Request from %s: %s" % (web.ctx.environ["REMOTE_ADDR"], web.ctx.path))

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
    vote_value = 1

    def GET(self):
        url = "http://%s%s" % (web.ctx.env["HTTP_HOST"], web.ctx.env["PATH_INFO"])

        return "This call requires a POST request and an auth token.  Example CLI use:\n\n" \
            "curl -X POST -d \"track_id=123&token=hello\" " \
            + url

    @send_json
    def POST(self):
        try:
            args = web.input(track_id="", token=None)
            logging.debug("Vote request: %s" % args)

            sender = auth.get_id_by_token(args.token)
            if sender is None:
                raise web.forbidden("Bad token.")

            if args.track_id.isdigit():
                track_id = int(args.track_id)
            else:
                track_id = tracks.get_last_track_id()

            weight = tracks.add_vote(track_id, sender, self.vote_value)
            if weight is None:
                return {"status": "error", "message": "No such track."}

            database.commit()

            message = 'OK, current weight of track #%u is %.04f.' % (track_id, weight)
            return {
                "status": "ok",
                "message": message,
                "id": track_id,
                "weight": weight,
            }
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

        track["current_ts"] = int(time.time())
        return track


class InfoController(Controller):
    @send_json
    def GET(self):
        track_id = web.input(id=None).id
        if track_id is None:
            return None

        track = tracks.get_track_by_id(track_id)
        if track is None:
            return None

        return track


class AuthController(Controller):
    def GET(self):
        args = web.input(token=None)
        if args.token is None:
            return "Please specify a token or POST."
        token = auth.confirm_token(args.token)
        if token:
            return "OK, tell this to your program: %s" % args.token
        else:
            return "Wrong token."

    @send_json
    def POST(self):
        args = web.input(id=None, type=None)
        token = auth.create_token(args.id, args.type)
        return {"status": "ok", "message": "You'll soon receive a message with a confirmation link."}


class IndexController(Controller):
    def GET(self):
        if not os.path.exists("static/index.html"):
            raise web.forbidden("Forbidden.")
        web.header("Content-Type", "text/html; charset=UTF-8")
        return file("static/index.html", "rb").read()


class SearchController(Controller):
    @send_json
    def GET(self):
        args = web.input(query=None)

        track_ids = tracks.find_ids(args.query)
        track_info = [database.Track.get_by_id(id) for id in track_ids]

        return {
            "status": "ok",
            "scope": "search",
            "tracks": track_info,
        }


class QueueController(Controller):
    @send_json
    def GET(self):
        args = web.input(track=None, token=None)

        if args.track:
            sender = auth.get_id_by_token(args.token)
            console.on_queue("-s " + str(args.track), sender or "Anonymous Coward")
            database.commit()

        return {"status": "ok"}


class RecentController(Controller):
    @send_json
    def GET(self):
        return {
            "status": "ok",
            "scope": "recent",
            "tracks": list(self.get_tracks()),
        }

    def get_tracks(self):
        for track in database.Track.find_recently_played():
            track["artist_url"] = track.get_artist_url()
            track["track_url"] = track.get_track_url()
            yield track


class TagCloudController(Controller):
    @send_json
    def GET(self):
        tags = database.Track.find_tags(cents=4)
        return {"status": "ok", "tags": tags}


def transaction_fix(handler):
    """Завершение предыдущей транзакции перед обработкой каждого запроса, иначе
    они все выполняются в рамках транзакции и не видят свежих данных."""
    try:
        return handler()
    finally:
        database.rollback()


def serve_http(hostname, port):
    """Starts the HTTP web server at the specified socket."""
    sys.argv.insert(1, "%s:%s" % (hostname, port))

    logging.info("Starting the ardj web service at http://%s:%s/" % (hostname, port))

    if "--debug" not in sys.argv:
        ScrobblerThread().start()

    app = web.application((
        "/", IndexController,
        "/api/auth(?:\.json)?", AuthController,
        "/api/status\.js(?:on)?", StatusController,
        "/api/tag/cloud\.json", TagCloudController,
        "/api/track/info\.json", InfoController,
        "/api/track/rocks\.json", RocksController,
        "/api/track/sucks\.json", SucksController,
        "/commit\.json", CommitController,
        "/track/info\.js(?:on)?", InfoController,
        "/track/next\.json", NextController,
        "/track/queue\.json", QueueController,
        "/track/recent\.json", RecentController,
        "/track/search\.json", SearchController,
    ))
    app.add_processor(transaction_fix)
    app.run()


def run_cli(args):
    """Starts the HTTP web server on the configured socket."""
    root = settings.get("webapi_root", "share/web")
    os.chdir(root)
    serve_http(*settings.get("webapi_socket", "127.0.0.1:8080").split(":", 1))


__all__ = ["serve_http", "run_cli"]  # hide unnecessary internals
