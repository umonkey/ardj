import os
import yaml

class wrapper:
    """Wraps a dictionary for easier access."""
    def __init__(self, data, filename):
        """Initializes the instance without any checking."""
        self.data = data
        self.filename = filename

    def get(self, key, default=None, fail=False):
        """Returns the value of the specified key.

        Key can be a path separated by slashes, e.g. foo/bar = ['foo']['bar'].
        If the path could not be resolved, default is returned."""
        data = self.data
        src_key = key
        for key in key.split('/'):
            if type(data) != dict or not data.has_key(key):
                if fail:
                    raise Exception('ERROR: %s not set.' % src_key)
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
            if not data.has_key(key):
                return False
            data = data[key]
        return True

    def __getitem__(self, key):
        """A convenience wrapper.

        Equals to get(key, None)."""
        return self.get(key)

    def __repr__(self):
        """Dumps the data for debugging purposes."""
        return '<ardj.settings.wrapper data=%s>' % self.data

wrapper_instance = None

def load():
    """Loads an object for accessing the config file.

    Instances are cached, subsequent calls will not cause the object to be
    reloaded."""
    global wrapper_instance
    if wrapper_instance is None:
        data = None
        for filename in ('~/.config/ardj/default.yaml', '/etc/ardj.yaml'):
            filename = os.path.expanduser(filename)
            if os.path.exists(filename):
                data = yaml.load(open(filename, 'rb'))
                break
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
