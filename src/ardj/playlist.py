import json
import os
import time
import yaml

import ardj.database
import ardj.settings


class Playlist(dict):
    static_data = None
    static_time = None
    static_name = None

    @classmethod
    def reload(cls, filename):
        cls.static_name = filename
        cls.static_time = None
        cls.static_data = None

    @classmethod
    def get_all(cls):
        """Returns playlist descriptions from the YAML file with last_played timestamps added."""
        stats = ardj.database.Open().get_playlist_times()
        result = []
        for playlist in cls.get_all_static():
            playlist["last_played"] = stats.get(playlist["name"], None)
            result.append(cls(playlist))
        return result

    @classmethod
    def get_active(cls, timestamp):
        """Returns playlists active at the specified moment."""
        result = []
        for pl in cls.get_all():
            if pl.is_active(timestamp):
                result.append(pl)
        return result

    @classmethod
    def get_all_static(cls):
        """Returns playlist definitions from the file."""
        if cls.static_name is None:
            cls.static_name = os.path.join(ardj.settings.getpath("musicdir", "~"), "playlists.yaml")
            if not os.path.exists(cls.static_name):
                return []
        if cls.static_time and cls.static_time < os.stat(cls.static_name).st_mtime:
            cls.static_data = None
        if cls.static_data is None:
            cls.static_data = cls.parse_file(file(cls.static_name, "rb").read())
            cls.static_time = os.stat(cls.static_name).st_mtime
        return cls.static_data

    @staticmethod
    def parse_file(contents):
        """Parses file contents, expands special values (days and hours)."""
        result = []
        for item in yaml.load(contents):
            if not isinstance(item, dict):
                continue
            for k, v in item.items():
                if k in ("days", "hours"):
                    values = []
                    for value in v:
                        if str(value).isdigit():
                            values.append(int(value))
                        elif '-' in str(value):
                            a, b = value.split('-')
                            values.extend(range(int(a), int(b) + 1))
                    item[k] = values
            if "labels" not in item:
                item["labels"] = [item["name"]]
            result.append(item)
        return result

    def is_active(self, timestamp):
        """Returns True if the playlist is active on that time."""
        ts = time.localtime(timestamp)

        if self.get("days"):
            now = int(time.strftime("%w", ts))
            if now not in self.get("days"):
                return False

        if self.get("hours"):
            now = int(time.strftime("%H", ts))
            if now not in self.get("hours"):
                return False

        if self.get("delay"):
            block_until = int(self["delay"]) * 60 + self["last_played"]
            if timestamp < block_until:
                return False

        return True

    def set_last_played(self, timestamp):
        """Modifies the last played time."""
        ardj.database.Open().set_playlist_time(self["name"], timestamp)

    def get_tracks(self, timestamp, cls=dict):
        """Returns all tracks (dicts)."""
        db = ardj.database.Open()
        args = {"labels": self["labels"]}
        if "repeat" in self:
            args["max_count"] = self["repeat"]
        if "track_delay" in self:
            args["track_delay"] = self["track_delay"]
        return [cls(x) for x in db.get_tracks(timestamp, **args)]


def cli_show_all(args):
    print json.dumps(Playlist.get_all(), indent=True)


def cli_show_active(args):
    print json.dumps(Playlist.get_active(int(time.time())), indent=True)
