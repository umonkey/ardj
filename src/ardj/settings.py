import yaml
import os

def load(app, defaults=None):
    for filename in ('/etc/ardj.conf', '~/.config/ardj.conf'):
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            tmp = yaml.load(open(filename, 'rb'))
            if type(tmp) == dict and tmp.has_key(app):
                return tmp[app]
            else:
                raise Exception('%s has no %s block.' % (filename, app))
    raise Exception('Config file ardj.conf not found.')
