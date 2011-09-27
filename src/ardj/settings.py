# vim: set fileencoding=utf-8:
#
# TODO:
# - reload data if file changes (all get() methods should check that).

import os
import sys
import yaml


class wrapper:
    """Wraps a dictionary for easier access."""
    def __init__(self, data, filename):
        """Initializes the instance without any checking."""
        self.data = data
        self.filename = filename

        self.playlists_mtime = None
        self.playlists_data = []

    def get(self, key, default=None, fail=False):
        """Returns the value of the specified key.

        Key can be a path separated by slashes, e.g. foo/bar = ['foo']['bar'].
        If the path could not be resolved, default is returned."""
        data = self.data
        src_key = key
        for key in key.split('/'):
            if type(data) != dict or key not in data:
                if fail:
                    raise KeyError('The "%s" setting is not set.' % src_key)
                return default
            data = data[key]
        return data

    def getpath(self, key, default=None, fail=False):
        """Returns a path specified by key.

        The value returned by get() is processed with os.path.expanduser()
        which makes the ~/ prefix available."""
        value = self.get(key, default, fail=fail)
        if value:
            value = os.path.expanduser(value)
        return value

    def list(self):
        """Do not use."""
        return type(self.data) == list and self.data or []

    def has_key(self, key):
        data = self.data
        for key in key.split('/'):
            if type(data) != dict:
                return False
            if key not in data:
                return False
            data = data[key]
        return True

    def get_music_dir(self):
        """
        Returns full path to the music folder.
        """
        return os.path.realpath(os.path.expanduser(self.get('musicdir', os.path.dirname(self.filename))))

    def get_playlists(self):
        filename = os.path.join(self.get_music_dir(), 'playlists.yaml')
        if not os.path.exists(filename):
            return []
        stat = os.stat(filename)
        if self.playlists_mtime is None or self.playlists_mtime < stat.st_mtime:
            self.playlists_mtime = stat.st_mtime
            self.playlists_data = yaml.load(open(filename, 'r').read())
        return self.playlists_data

    def __getitem__(self, key):
        """A convenience wrapper.

        Equals to get(key, None)."""
        return self.get(key)

    def __repr__(self):
        """Dumps the data for debugging purposes."""
        return '<ardj.settings.wrapper data=%s>' % self.data

wrapper_instance = None

def load_data():
    """Returns the raw contents of the config file.

    Options: ARDJ_SETTINGS envar, ~/.config/ardj/default.yaml, /etc/ardj.yaml.
    If none exist, an empty dicrionary returned.
    """
    for filename in (os.environ.get('ARDJ_SETTINGS'), '~/.config/ardj/default.yaml', '/etc/ardj.yaml'):
        if filename:
            filename = os.path.expanduser(filename)
            if os.path.exists(filename):
                return yaml.load(open(filename, 'rb')), filename
    return {}, None


def load(refresh=False):
    """Loads an object for accessing the config file.

    Instances are cached, subsequent calls will not cause the object to be
    reloaded."""
    global wrapper_instance
    if wrapper_instance is None or refresh:
        data, filename = load_data()
        wrapper_instance = wrapper(data, filename)
    return wrapper_instance


def get(key, default=None, fail=False):
    """get(k, v) <==> load().get(k, v)"""
    return load().get(key, default, fail=fail)

def getpath(key, default=None, fail=False):
    """getpath(k, v) <==> load().getpath(k, v)"""
    return load().getpath(key, default, fail=fail)

def edit_cli(args):
    editor = os.getenv('EDITOR', 'editor')
    os.system(editor + ' ' + load().filename)

def get_music_dir():
    return load().get_music_dir()
