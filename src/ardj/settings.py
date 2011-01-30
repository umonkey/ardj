import yaml
import os

def load(app, defaults=None):
    defaults = defaults or {}
    for filename in ('/etc/ardj.conf', '~/.config/ardj.conf'):
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            tmp = yaml.load(open(filename, 'rb'))
            if type(tmp) == dict and tmp.has_key(app):
                defaults.update(tmp[app])
    return defaults
