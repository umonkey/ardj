import yaml
import os

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
    return defaults
