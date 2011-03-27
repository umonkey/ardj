# vim: set fileencoding=utf-8:

import json
import os
import sys
import time
import urllib2
from sqlite3 import dbapi2 as sqlite

import ardj.settings
import ardj.website

DEFAULT_DATABASE = '/var/log/icecast2/access.sqlite'
DEFAULT_CACHE_FILE = '/tmp/ardj-listeners.json'
DEFAULT_MAP_FILE = '/tmp/ardj-listeners.js'

settings = None

def fetch(url):
    return urllib2.urlopen(urllib2.Request(url)).read()

def locate_freegeoip(ip):
    data = json.loads(fetch('http://freegeoip.net/json/' + ip))
    if data['latitude'] and data['longitude'] and data['latitude'] != '0':
        return (data['latitude'], data['longitude'])

def locate_ip(ip):
    data = locate_freegeoip(ip)
    if data is None:
        pass # locate_somewhere_else()
    return data

def get_recent_ips():
    dbname = settings.getpath('database', DEFAULT_DATABASE)
    if not os.path.exists(dbname):
        print >>sys.stderr, 'SQLite database not found: %s' % dbname
        return {}
    cur = sqlite.connect(dbname).cursor()
    limit = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 60 * 60 * 24 * 30))
    cur.execute('SELECT DISTINCT remote_addr FROM log WHERE date >= ?', (limit, ))
    return dict([(str(row[0]), None) for row in cur.fetchall()])

def locate_ips(ips):
    cache = {}
    cache_fn = settings.getpath('cache', DEFAULT_CACHE_FILE)
    if os.path.exists(cache_fn):
        cache = json.loads(open(cache_fn, 'rb').read())

    for ip in ips.keys():
        if cache.has_key(ip):
            ips[ip] = ','.join(cache[ip])
        else:
            data = locate_ip(ip)
            if data:
                loc = (data['latitude'], data['longitude'])
                cache[ip] = loc
                ips[ip] = ','.join(loc)
                print ip, ips[ip]
            else:
                print '%s not found.' % ip
                del ips[ip]

    open(cache_fn, 'wb').write(json.dumps(cache))
    return ips

def get_stats(ips):
    result = []
    for loc in list(set(ips.values())):
        lat, lon = loc.split(',')
        result.append({
            'll': [lat, lon],
            'html': u'Подключений: %s.' % len([x for x in ips.keys() if ips[x] == loc]),
        })
    return result

def get_bounds(markers):
    return [
        min([m['ll'][0] for m in markers]),
        max([m['ll'][0] for m in markers]),
        min([m['ll'][1] for m in markers]),
        max([m['ll'][1] for m in markers]),
    ]

def export_map(markers):
    js = 'var map_data = %s;' % json.dumps({ 'bounds': get_bounds(markers), 'markers': markers }, indent=True)
    filename = settings.getpath('data_js', DEFAULT_MAP_FILE)
    open(filename, 'wb').write(js.encode('utf-8'))
    print 'Wrote %s' % filename

def update_listeners():
    global settings
    settings = ardj.settings.load('listeners_map')

    ips = get_recent_ips()
    if not len(ips):
        print >>sys.stderr, 'No listeners.'
        sys.exit(1)

    ips = locate_ips(ips)
    markers = get_stats(ips)
    export_map(markers)
    ardj.website.update(settings.get('make_target', 'autoupdate'))
