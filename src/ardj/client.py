# vim: set fileencoding=utf-8:

"""The media database client.

Performs commands on local and/or remote ardj media databases."""

import StringIO
import json
import os
import sys

import ardj.settings
import ardj.util

USAGE = """Usage: ardj client command args...

Commands:
  purge                        -- remove dead files
  queue track_id               -- queue a track
  add_track filename [-queue]  -- add a file to the database and queue it
"""

class LocalClient:
    def __init__(self, path):
        if not os.path.exists(path):
            raise Exception('Local database does not exists: %s' % path)
        self.database = path


class RemoteClient:
    def __init__(self, config):
        proto, host, path = config.split(':', 2)
        if proto != 'ssh':
            raise Exception('Remote ardj client only works over ssh.')
        self.host = host
        self.path = path

    def queue_track(self, track_id):
        """Schedule the track for playing asap."""
        self.call_remote([{
            'method': 'queue_track',
            'args': [track_id],
        }])

    def add_track(self, filename, queue=False):
        """Add a track to the database."""
        self.call_remote([{
            'method': 'add_track',
            'args': [filename],
            'kwargs': { 'queue': queue }
        }])

    def get_stats(self):
        """Shows database statistics."""
        print self.call_remote([{
            'method': 'get_stats',
        }])

    def purge(self):
        """Removes files that need to be deleted."""
        self.call_remote([{
            'method': 'purge',
        }])

    def call_remote(self, args):
        data = json.dumps(args)
        ardj.log.debug('Calling remote ardj with: ' + data)
        ardj.util.run([ 'ssh', self.host, self.path, 'client', 'exec' ], stdin_data=data)


def Open():
    """Returns an instance of the client."""
    config = ardj.settings.get('database')
    if 'local' in config:
        return LocalClient(config['local'])
    elif 'remote' in config:
        return RemoteClient(config['remote'])
    else:
        raise Exception('Client not configured (neither database/local nor database/remote not set).')


def run_cli(args):
    """Implements the "ardj client" command."""
    cli = Open()
    if len(args) and args[0] == 'exec':
        for call in json.loads(sys.stdin.read()):
            func = call['method']
            args = 'args' in call and call['args'] or []
            kwargs = 'kwargs' in call and call['kwargs'] or {}
            getattr(cli, func)(*args, **kwargs)
        return
    elif len(args) and args[0] == 'purge':
        return cli.purge()

    print USAGE
