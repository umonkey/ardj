import yaml
import os

def load(app, defaults=None, quiet=False):
    for filename in ('/etc/ardj.conf', '~/.config/ardj.conf'):
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            tmp = yaml.load(open(filename, 'rb'))
            if type(tmp) == dict and tmp.has_key(app):
                defaults = defaults or {}
                defaults.update(tmp[app])
                return defaults
            elif defaults is not None:
                return defaults
            elif quiet:
                return {}
            else:
                raise Exception('%s has no %s block.' % (filename, app))
    raise Exception('Config file ardj.conf not found.')
