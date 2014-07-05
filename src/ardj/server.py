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


HELP_PAGE = u"""<!doctype html>
<html>
 <head>
  <title>ardj web api</title>
  <style type="text/css">
    pre { background-color: #eee; border-left: solid 4px #888; padding: 10px 10px 10px 20px; }
    h2 { font-family: monospace; margin-top: 3em }
  </style>
 </head>
 <body>
    <h1>Добро пожаловать в веб-интерфейс к ardj</h1>
    <p>Вы попали на веб-сервер, встроенный в программный комплекс ardj.  Этот веб-сервер обслуживает запросы к базе данных радиостанции.  С его помощью можно писать приложения, которые управляют эфиром.</p>
    <p>WebAPI позволяет сторонним приложениям общаться со станцией используя протоколы HTTP и JSON.  Результат всегда возвращается в виде отформатированного JSON объекта, с отступами и юникодными символами.</p>
    <p>При использовании расширения <code>.js</code> результат возвращается в виде готового фрагмента скрипта, пригодного для включения в HTML-страницу.  По умолчанию значение записывается в переменную <code>response</code>, другое название можно указать с помощью параметра <code>var</code>, а с помощью параметра <code>callback</code> можно указать имя функции, которая должна быть выполнена после присвоения переменной значения.  Пример:</p>
    <pre>$ curl 'http://music.tmradio.net/status.js?var=foo&amp;callback=bar'
var foo = {...}; bar(foo);</pre>

    <p>Эту страницу можно заменить, положив нужные файлы (включая <code>index.html</code>) в папку <code>%(path)s/static</code>.  После размещения файла <code>index.html</code> на эту страницу (с документацией) можно будет попасть по адресу <code>/help</code>.</p>

    <h2>auth.json</h2>
    <p>Используется для получения токена.  Запрос следует отправлять методом POST, идентификатор пользователя и его тип (jid или email) указываются параметрами <code>id</code> и <code>type</code>.  Возвращает серверное сообщение, пользователь получает дальнейшие инструкции через jabber или email.  Пример:</p>
    <pre>$ curl -X POST -d 'id=alice@example.com&amp;type=email' 'http://music.tmradio.net/auth.json'
{
  "status": "ok",
  "message": "You'll soon receive a message with a confirmation link."
}</pre>

    <p>После этого пользователь получает ссылку для подтверждения токена, который сообщает программе.  С помощью токена можно <a href="#rocks">голосовать</a>.</p>

    <p><strong>Внимание</strong>: при запросе токена пользователю отправляется ссылка, в создании которой участвует значение переменной <code>web_api_root</code> конфигурационного файла.  По умолчанию эта переменная содержит значение <code>http://localhost:8080</code> — адрес, непригодный для использования за пределами сервера.  Чтобы сторонние пользователи могли получить доступ к системе аутентификации, нужно записать в эту переменную имеющийся в распоряжении сервера публичный адрес, например: <code>http://api.myradio.com</code>.</p>

    <p>Для подтверждения токена пользователя с помощью сообщения по почте отправляют на адрес <code>auth.json?token=XXXXXX</code>.  При переходе на этот адрес токен становится активным, пригодным для использования.  Эта процедура нужна для того, чтобы проверить действительность почтового адреса пользователя, запросившего токен.  Это исключает использование сфабрикованных адресов и сокращает возможность накрутки голосов.</p>

    <h2 id="playlist">playlist.json</h2>
    <p>Выводит информацию о содержимом плейлиста.  Имя плейлиста можно указать в параметре <code>name</code>: all — все композиции, never — никогда не звучавшие, recent — звучавшие недавно, другое значение воспринимается как название метки.  Параметр <code>artist</code> может содержать имя исполнителя, если нужна дополнительная фильтрация по нему.  Параметр <code>tag</code> может содержать метку, если нужна дополнительная фильтрация по ней.  Пример:</p>
    <pre>$ curl http://music.tmradio.net/playlist.json?tag=rock
{
 "artists": [
  "Duran Duran",
  "Guns N' Roses"
 ],
 "tracks": [
  {
   "title": "Come Undone",
   "id": 6,
   "artist": "Duran Duran"
  },
  {
   "title": "Too Much Information",
   "id": 5,
   "artist": "Duran Duran"
  },
  {
   "title": "Don't Cry (Original)",
   "id": 9,
   "artist": "Guns N' Roses"
  },
  {
   "title": "November Rain",
   "id": 7,
   "artist": "Guns N' Roses"
  },
  {
   "title": "Sweet Child O' Mine",
   "id": 8,
   "artist": "Guns N' Roses"
  }
 ],
 "artsits": [],
 "tags": [
  "rock"
 ]
}</pre>

    <h2 id="status">status.json</h2>
    <p>Возвращает информацию о проигрываемой на данный момент композиции.  Формат результата аналогичен <a href="#info">track/info.json</a>.  Пример:</p>
    <pre>$ curl http://music.tmradio.net/track/info.json
{
  "real_weight": 1.8666666666666667,
  "last_played": 1326743103,
  "weight": 1.8666666666666667,
  "image": null,
  "labels": [ "news", "preroll-not-wanted", "special" ],
  "download": null,
  "id": 4598,
  "count": 5955,
  "filepath": "/home/radio/Music/echo-msk-news.ogg",
  "artist": "Эхо Москвы",
  "title": "Новости",
  "filename": "echo-msk-news.ogg",
  "length": 97
}</pre>

    <h2 id="cloud">tag/cloud.json</h2>
    <p>Возвращает информацию обо всех тэгах и количестве использований.  Игнорирует тэги, использованные менее чем в 5 композициях.  Пример:</p>
    <pre>$ curl -X GET http://music.tmradio.net/tag/cloud.json
{
  "status": "ok",
  "tags": {
    "lounge": 5,
    "music": 22
    "rock": 17,
  }
}</pre>

    <h2 id="queue">track/queue.json</h2>
    <p>Добавляет композицию в очередь для скорейшего проигрывания.  Параметр <code>track</code> должен содержать идентификатор композиции (пользователь обычно получает его с помощью вызова <a href="#playlist">playlist.json</a>).  Пример:</p>
    <pre>$ curl http://music.tmradio.net/track/queue.json?track=1562&token=deadbeef
{
  "success": true
}</pre>

    <h2 id="recent">track/recent.json</h2>
    <p>Возвращает список недавно игравших композиций.  Пример:</p>
    <pre>$ curl http://music.tmradio.net/track/recent.json
{
  "success": true,
  "scope": "recent",
  "tracks": [...]
}</pre>

    <h2 id="rocks">track/rocks.json</h2>
    <p>Записывает одобрение пользователем текущей композиции.  Для голосования за композицию, звучавшую ранее, её идентификатор можно указать в параметре <code>id</code>.</p>
    <p>Запросы нужно отправлять методом POST, указав полученный при аутентификации токен.  Пример:</p>
    <pre>$ curl -X POST -d 'token=baadf00d&amp;track_id=123' http://music.tmradio.net/track/rocks.json
{
  "status": "ok",
  "message": "OK, current weight of track #123 is 2.9333."
}</pre>

    <h2 id="search">track/search.json</h2>
    <p>Возвращает информацию о композициях, удовлетворяющих запросу.  Пример:</p>
    <pre>$ curl http://music.tmradio.net/track/search.json?query=amadeus
{
  "success": true,
  "scope": "search",
  "tracks": [...]
}</pre>

    <h2 id="sucks">track/sucks.json</h2>
    <p>Записывает неодобрение пользователем текущей композиции.  Для голосования против композиции, звучавшей ранее, её идентификатор можно указать в параметре <code>id</code>.</p>
    <p>Запросы нужно отправлять методом POST, указав полученный при аутентификации токен.  Пример:</p>
    <pre>$ curl -X POST -d 'token=baadf00d&amp;track_id=123' http://music.tmradio.net/track/sucks.json
{
  "status": "ok",
  "message": "OK, current weight of track #123 is 1.9333."
}</pre>

    <h2 id="update">track/update.json</h2>
    <p>Изменяет информацию о песне.</p>
    <p>Запросы нужно отправлять методом POST, указав полученный при <a href="#auth">аутентификации</a> токен.  Пример:</p>
    <pre>$ curl -X POST -d 'token=baadf00d&amp;id=123&amp;artist=KMFDM&amp;title=Money&amp;tag=electronic&amp;tag=music' http://music.tmradio.net/track/update.json
{
  "success": true
}</pre>
    <p>Обновляет свойства <code>artist</code> и <code>title</code> только если они переданы.  Если указан один или несколько параметров <code>tag</code> — все старые метки заменяются новыми.</p>

    <h2 id="info">track/info.json</h2>
    <p>Возвращает информацию о композиции идентификатор которой указан в параметре <code>id</code>.  Пример:</p>
    <pre>$ curl 'http://music.tmradio.net/track/info.json?id=6065'
{
 "real_weight": 1.0,
 "last_played": 1326743926,
 "weight": 1.1499999999999999,
 "image": "http://userserve-ak.last.fm/serve/64s/30245783.jpg",
 "labels": [ "calm", "female", "fresh", "music", "vocals", "source:jamendo.com" ],
 "download": null,
 "id": 6065,
 "count": 5,
 "filepath": "/radio/music/7/4/746fee45f4b312d28bba71b7cb2529fa.ogg",
 "artist": "KOOQLA",
 "title": "In my mind",
 "filename": "7/4/746fee45f4b312d28bba71b7cb2529fa.ogg",
 "length": 296
}</pre>
 </body>
</html>
"""


def log_debug(msg, *args, **kwargs):
    return logging.debug(msg.format(*args, **kwargs))


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


class Controller:
    def __init__(self):
        logging.debug("Request from %s: %s" % (web.ctx.environ["REMOTE_ADDR"], web.ctx.path))

    def __del__(self):
        logging.debug("Request finished, closing the transaction.")
        database.commit()


class AuthController(Controller):
    def GET(self):
        args = web.input(token=None)
        if args.token is None:
            web.header("Content-Type", "text/plain; charset=utf-8")
            return "Please specify a token or POST."
        token = auth.confirm_token(args.token)
        if token:
            web.header("Content-Type", "text/plain; charset=utf-8")
            return "OK, tell this to your program: %s" % args.token
        else:
            web.header("Content-Type", "text/plain; charset=utf-8")
            return "Wrong token."

    @send_json
    def POST(self):
        args = web.input(id=None, type=None)
        token = auth.create_token(args.id, args.type)
        return {"status": "ok", "message": "You'll soon receive a message with a confirmation link."}


class HelpController(Controller):
    """Implements the built-in web api help page."""
    def GET(self):
        web.header("Content-Type", "text/html; charset=utf-8")
        return HELP_PAGE % {
            "path": get_web_root().rstrip("/"),
        }


class IndexController(Controller):
    def GET(self):
        root = settings.get("webapi_root")
        filename = os.path.join(root, "static", "index.html")
        if os.path.exists(filename):
            web.header("Content-Type", "text/html; charset=UTF-8")
            with open(filename, "rb") as f:
                return f.read()

        return HelpController().GET()


class InfoController(Controller):
    @send_json
    def GET(self):
        args = web.input(id=None, token=None)
        sender = auth.get_id_by_token(args.token)

        track_id = args.id
        if track_id is None:
            return None

        track = tracks.get_track_by_id(track_id, sender=sender)
        if track is None:
            return None

        return track


class PlaylistController(Controller):
    @send_json
    def GET(self):
        args = web.input(name="all", artist=None, tag=None)

        playlist_name = args["name"]
        if playlist_name == "bookmarks":
            playlist_name = "bm:hex@umonkey.net"

        artist_name = args["artist"]
        if artist_name == "All artists":
            artist_name = None

        tag_name = args["tag"]
        if tag_name == "All tags":
            tag_name = None

        print "Playlist query: %s" % dict(args)

        result = {"artsits": [], "tags": [], "tracks": []}
        result["artists"] = [a["name"] for a in database.Artist.query(
            playlist=playlist_name, tag=tag_name)]
        result["tags"] = database.Label.query_names(
            playlist=playlist_name, artist=artist_name)

        tracks = database.Track.query(
            playlist=playlist_name, artist=artist_name, tag=tag_name)
        result["tracks"] = [{"id": t["id"], "artist": t["artist"],
            "title": t["title"]} for t in tracks]

        return result


class QueueController(Controller):
    @send_json
    def GET(self):
        args = web.input(track=None, token=None)

        if args.track:
            sender = auth.get_id_by_token(args.token)
            console.on_queue("-s " + str(args.track), sender or "Anonymous Coward")
            database.commit()
            return {"success": True}

        return {"success": False,
            "error": "track id not specified"}


class RaiseController(Controller):
    """Выброс исключения (для тестирования обработки исключений)."""
    def GET(self):
        raise Exception("Hello, world!")


class RecentController(Controller):
    @send_json
    def GET(self):
        return {
            "success": True,
            "scope": "recent",
            "tracks": list(self.get_tracks()),
        }

    def get_tracks(self):
        for track in database.Track.find_recently_played():
            track["artist_url"] = track.get_artist_url()
            track["track_url"] = track.get_track_url()
            yield track


class RocksController(Controller):
    vote_value = 1

    def GET(self):
        args = web.input(track_id="123", token="sEkReT")
        url = "http://%s%s" % (web.ctx.env["HTTP_HOST"], web.ctx.env["PATH_INFO"])

        web.header("Content-Type", "text/plain; charset=utf-8")
        return u"This call requires a POST request and an auth token.  Example CLI use:\n\n" \
            "curl -X POST -d \"track_id=%s&token=%s\" %s" \
            % (args.track_id, args.token, url)

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
            log.log_exception(str(e), e)
            return {"status": "error", "message": str(e)}


class SearchController(Controller):
    @send_json
    def GET(self):
        args = web.input(query=None)

        track_ids = tracks.find_ids(args.query)
        track_info = [database.Track.get_by_id(id) for id in track_ids]

        return {
            "success": True,
            "scope": "search",
            "tracks": track_info,
        }


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


class SucksController(RocksController):
    vote_value = -1


class TagCloudController(Controller):
    @send_json
    def GET(self):
        tags = database.Track.find_tags(
            cents=4, min_count=1)
        return {"status": "ok", "tags": dict(tags)}


class UpdateTrackController(Controller):
    @send_json
    def POST(self):
        args = web.input(
            token=None,
            id=None,
            title=None,
            artist=None,
            tag=[])

        sender = auth.get_id_by_token(args.token)
        if sender is None:
            return {"success": False,
                "error": "bad token"}

        track = database.Track.get_by_id(int(args.id))
        if track is None:
            return {"success": False,
                "error": "track not found"}

        if args.artist:
            track["artist"] = args.artist
            log_debug("{0} set artist for track {1} to {2}",
                sender, args.id, args.artist)
        if args.title:
            track["title"] = args.title
            log_debug("{0} set title for track {1} to {2}",
                sender, args.id, args.title)
        track.put()

        if args.tag:
            track.set_labels(args.tag)
            log_debug("{0} set labels for track {1} to {2}",
                sender, args.id, ", ".join(args.tag))

        database.commit()

        return {"success": True}


class ExceptionHandlingMiddleWare(object):
    """Завершение предыдущей транзакции после обработки каждого запроса, для
    исключения блокировки базы данных."""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        finally:
            database.rollback()


def serve_http(hostname, port):
    """Starts the HTTP web server at the specified socket."""
    sys.argv.insert(1, "%s:%s" % (hostname, port))

    logging.info("Starting the ardj web service at http://%s:%s/" % (hostname, port))

    app = web.application((
        "/", IndexController,
        "/help/?", HelpController,
        "/auth(?:\.json)?", AuthController,
        "/playlist\.json", PlaylistController,
        "/raise", RaiseController,  # for testing, important.
        "/status\.js(?:on)?", StatusController,
        "/tag/cloud\.json", TagCloudController,
        "/track/info\.js(?:on)?", InfoController,
        "/track/info\.json", InfoController,
        "/track/queue\.json", QueueController,
        "/track/recent\.js(?:on)?", RecentController,
        "/track/rocks\.json", RocksController,
        "/track/search\.json", SearchController,
        "/track/sucks\.json", SucksController,
        "/track/update\.json", UpdateTrackController,
    ))
    app.run(ExceptionHandlingMiddleWare)


def get_web_root():
    root = settings.get("webapi_root")
    if root is None or not os.path.exists(root):
        my_path = os.path.realpath(__file__)
        if my_path.startswith(os.path.expanduser("~/")):
            logging.warning("Using built-in web interface.")
            root = os.path.join(os.path.dirname(os.path.dirname(
                os.path.dirname(my_path))), "share/web")
    return root


def cmd_serve():
    """Starts the HTTP web server on the configured socket."""
    database.init_database()

    root = get_web_root()
    if root is None:
        logging.error("Could not find web root folder.")
        sys.exit(1)

    logging.info("Web root is %s" % root)

    os.chdir(root)
    serve_http(*settings.get("webapi_socket", "127.0.0.1:8080").split(":", 1))


def cmd_tokens():
    """List valid tokens."""
    from ardj.auth import get_active_tokens
    for t in get_active_tokens():
        print "%s: %s" % (t["login"], t["token"])


__all__ = ["cmd_serve", "cmd_tokens"]  # hide unnecessary internals
