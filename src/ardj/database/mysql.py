import os
import random
import sys

from MySQLdb import connect
from MySQLdb.constants import FIELD_TYPE


class MySQL(object):
    def __init__(self, **kwargs):
        self.db = None
        self.args = kwargs

    def connect(self):
        if self.db is None:
            self.db = connect(conv={
                FIELD_TYPE.VAR_STRING: lambda s: s.decode("utf-8"),
                FIELD_TYPE.LONG: int,
                FIELD_TYPE.DOUBLE: float,
            }, **self.args)
            self.query("SET NAMES UTF8")

    def run_cli(self):
        argmap = {"host":"host", "user":"user", "password":"password"}

        cmd = ["mysql"]
        for k, v in argmap.items():
            if k in self.args:
                cmd.append("--%s=%s" % (k, self.args[k]))
        cmd.append(self.args["db"])

        import subprocess
        subprocess.Popen(cmd).wait()

    def get_tracks_to_scrobble(self, skip_labels=None, min_length=60):
        """Returns tracks to scrobble (a list of dictionaries with keys artist,
        title, ts).  Picks records from table 'playlog' which have lastfm set
        to 0 and which have corresponding tracks not deleted."""
        if skip_labels is None:
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.length > ? ORDER BY p.ts'
            params = [min_length]
        elif not isinstance(skip_labels, (list, tuple)):
            raise TypeError("skip_labels must be a list or a tuple.")
        else:
            inner = ", ".join(["?"] * len(skip_labels))
            sql = 'SELECT t.artist, t.title, p.ts FROM tracks t INNER JOIN playlog p ON p.track_id = t.id WHERE p.lastfm = 0 AND t.weight > 0 AND t.length > ? AND t.id NOT IN (SELECT track_id FROM labels WHERE label IN (%s)) ORDER BY p.ts' % inner
            params = [min_length] + skip_labels

        return self.select(sql, params, ["artist", "title", "ts"])

    def set_track_scrobbled(self, ts):
        self.query("UPDATE playlog SET lastfm = 1 WHERE ts = ?", [ts])

    def get_playlist_times(self):
        """Returns a dictionary which describes when which playlist was last
        used.  Keys are playlist names, values are UNIX timestamps."""
        return dict(self.select("SELECT name, last_played FROM playlists"))

    def set_playlist_time(self, name, timestamp):
        """Modifies the playlist timestamp."""
        self.query("DELETE FROM playlists WHERE name = ?", [name])
        self.query("INSERT INTO playlists (name, last_played) VALUES (?, ?)", [name, int(timestamp)])

    def erase_tracks(self):
        """Deletes all tracks."""
        self.query("DELETE FROM tracks")

    def add_track(self, artist=None, title=None, weight=None, real_weight=None, filename=None, labels=None, owner=None, play_count=None, last_played=None):
        """Inserts a new track."""
        if weight is None:
            weight = 1.0
        if real_weight is None:
            real_weight = 1.0
        if last_played is None:
            last_played = 0
        if play_count is None:
            play_count = 0

        self.query("INSERT INTO tracks (artist, title, weight, real_weight, filename, last_played, count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [artist, title, weight, real_weight, filename, last_played, play_count])
        track_id = self.db.insert_id()
        if labels is not None:
            for label in labels:
                self.add_track_label(track_id, label)
        return track_id

    def get_track_by_id(self, track_id):
        tracks = self.select("SELECT id, artist, title, weight, real_weight, filename, last_played, count FROM tracks WHERE id = ?", [track_id],
            fields=["id", "artist", "title", "weight", "real_weight", "filename", "last_played", "count"])
        if tracks:
            return tracks[0]

    def add_track_label(self, track_id, label, email=None):
        if email is None:
            email = 'unknown'
        self.query("INSERT INTO labels (track_id, label, email) VALUES (?, ?, ?)", [track_id, label, email])

    def get_track_labels(self, track_id):
        """Returns all labels applied to a track."""
        labels = self.select("SELECT label FROM labels WHERE track_id = ?", [track_id])
        return list(set([l[0] for l in labels]))

    def get_tracks(self, timestamp=None, artist=None, title=None, labels=None, max_count=None, min_weight=None, max_weight=None, track_delay=None, has_filename=False):
        sql = "SELECT id, artist, title, weight, real_weight, filename, last_played, count FROM tracks"

        where = []
        params = []

        if artist is not None:
            where.append("artist = ?")
            params.append(artist)

        if title is not None:
            where.append("title = ?")
            params.append(title)

        if has_filename:
            where.append("filename IS NOT NULL")

        if max_count is not None:
            where.append("count < ?")
            params.append(max_count)

        if track_delay is not None and timestamp is not None:
            where.append("last_played < ?")
            params.append(timestamp - int(track_delay) * 60)

        if min_weight is None:
            where.append("weight > ?")
            params.append(0)
        else:
            where.append("weight >= ?")
            params.append(min_weight)

        if max_weight is not None:
            where.append("weight <= ?")
            params.append(max_weight)

        if labels is not None:
            rest = []
            for label in list(set(labels)):
                if label.startswith('-'):
                    where.append("id NOT IN (SELECT track_id FROM labels WHERE label = ?)")
                    params.append(label[1:])
                elif label.startswith('+'):
                    where.append("id IN (SELECT track_id FROM labels WHERE label = ?)")
                    params.append(label[1:])
                else:
                    rest.append(label)
            if rest:
                qmarks = ', '.join(['?'] * len(rest))
                where.append("id IN (SELECT track_id FROM labels WHERE label IN (%s))" % qmarks)
                params.extend(rest)

        if where:
            sql += ' WHERE ' + ' AND '.join(where)

        return self.select(sql, params, ["id", "artist", "title", "weight", "real_weight", "filename", "last_played", "count"])

    def get_random_track(self, timestamp, touch=False, **kwargs):
        tracks = self.get_tracks(timestamp, **kwargs)
        if not tracks:
            return None
        track = random.choice(tracks)
        if touch:
            self.set_track_played(track["id"], timestamp)
            track["last_played"] = timestamp
        return track

    def update_track(self, track):
        """Updates track info."""
        if not isinstance(track, dict):
            raise TypeError("track must be a dictionary")
        if "id" not in track:
            raise ValueError("track has no id")

        sql = "UPDATE tracks SET "
        parts = []
        params = []

        for k, v in track.items():
            if k in ("artist", "title", "last_played", "count", "weight", "real_weight", "filename"):
                parts.append(k + " = ?")
                params.append(v)
        sql += ", ".join(parts)

        if not parts:
            return

        sql += " WHERE id = ?"
        params.append(track["id"])

        self.query(sql, params)

    def get_track_votes(self, track_id):
        return self.select("SELECT v.email, v.vote * k.weight FROM votes v INNER JOIN karma k ON k.email = v.email WHERE v.track_id = ? ORDER BY v.ts", [track_id], ["email", "vote"])

    def set_track_played(self, track_id, ts):
        """Updates track's last_played timestamp."""
        self.query("UPDATE tracks SET count = count + 1, last_played = ? WHERE id = ?", [ts, track_id])
        # TODO: weight/real_weight

    def get_last_played_artists(self, count=10):
        """Returns count names of recently played artists."""
        names = []
        for name in self.select("SELECT artist FROM tracks ORDER BY last_played DESC"):
            if name not in names:
                names.append(name)
            if len(names) == count:
                break
        return names

    def get_queue(self):
        """Returns queue status."""
        return self.select("SELECT id, track_id, owner FROM queue ORDER BY id", fields=["id", "track_id", "owner"])

    def add_to_queue(self, track_id, owner=None):
        """Adds a track to the queue."""
        self.query("INSERT INTO queue (track_id, owner) VALUES (?, ?)", [track_id, owner])

    def remove_from_queue(self, queue_id):
        self.query("DELETE FROM queue WHERE id = ?", [queue_id])

    # ---------- LOW LEVEL STUFF ----------

    def select(self, sql, params=None, fields=None):
        """Returns rows, returned by the specified query.  Optionally maps to a
        dictionary according to fields."""
        self.connect()
        sql = self.format_sql(sql, params)
        self.log_query(sql)
        cur = self.db.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        if fields is not None:
            rows = [self.map_row(row, fields) for row in rows]
        return rows

    def query(self, sql, params=None):
        self.connect()
        sql = self.format_sql(sql, params)
        self.log_query(sql)
        return self.db.query(sql)

    def format_sql(self, sql, params=None):
        """MySQLdb does not support parameters, so we need to fake them."""
        if params is None:
            params = []
        params = list(params)

        parts = str(sql).split('?')
        for idx, part in enumerate(parts):
            if params:
                value = params[0]
                if value is None:
                    value = "NULL"
                elif isinstance(value, (int, long, float)):
                    value = str(value)
                else:
                    value = self.db.escape_string(value.encode("utf-8"))
                    value = "'%s'" % value
                parts[idx] += value
                del params[0]

        return ''.join(parts)

    def map_row(self, row, fields):
        return dict([(fields[idx], value) for idx, value in enumerate(row)])

    def log_query(self, sql):
        if os.environ.get("ARDJ_DEBUG_SQL"):
            print >>sys.stderr, "Running SQL: %s" % sql


Open = MySQL
