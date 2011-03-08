import yaml
import os

class wrapper:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        if self.data is not None:
            if self.data.has_key(key):
                return self.data[key]
        return default

    def getpath(self, key, default=None):
        value = self.get(key, default)
        if value:
            value = os.path.expanduser(value)
        return value

    def has_key(self, key):
        return self.data and self.data.has_key(key)

    def __getitem__(self, key):
        return self.get(key)

    def __repr__(self):
        return '<ardj.settings.wrapper data=%s>' % self.data

def load(app, defaults=None):
    defaults = defaults or {}
    for filename in ('~/.config/ardj/default.yaml', '/etc/ardj.yaml'):
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            tmp = yaml.load(open(filename, 'rb'))
            if type(tmp) == dict and tmp.has_key(app):
                if type(tmp[app]) == dict:
                    defaults.update(tmp[app])
                else:
                    defaults = tmp[app]
    return wrapper(defaults)
