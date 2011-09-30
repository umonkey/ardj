"""ARDJ, an artificial DJ.

This module contains the command line interface.  It first initializes the log
file, then, depending on the command line arguments, loads and executes the
appropriate submodule."""

import logging
import os
import sys
import traceback

import ardj.log

COMMAND_MAP = [ # (command, module, function, description)
    ('client', 'client', 'run_cli', 'run the client'),
    ('config', 'settings', 'edit_cli', 'edit settings'),
    ('console', 'console', 'run_cli', 'jabber-like CLI'),
    ('db', 'database', 'run_cli', 'database functions'),
    ('db-init', 'database', 'cli_init', 'initializes the database'),
    ('events', 'tout', 'run_cli', 'works with the upcoming events'),
    ('find-new-tracks', 'tracks', 'find_new_tracks', 'fetch new songs from Last.fm'),
    ('hotline', 'hotline', 'run_cli', 'work with the hotline'),
    ('icelog', 'icelogger', 'run_cli', 'work with Icecast logs'),
    ('jabber', 'jabber', 'run_cli', 'run the jabber bot'),
    ('listeners', 'listeners', 'run_cli', 'summarizes listeners.csv'),
    ('mail', 'mail', 'run_cli', 'send or receive mail'),
    ('map-listeners', 'map', 'update_listeners', 'updates the listeners map'),
    ('merge-votes', 'database', 'merge_votes', 'merge votes according to jabber/aliases'),
    ('news', 'news', 'run_cli', 'updates news from echo.msk.ru'),
    ('rg', 'replaygain', 'run_cli', 'scan ReplayGain in files'),
    ('say', 'speech', 'render_text_cli', 'renders text to voice using festival, then plays it'),
    ('serve', 'server', 'run_cli', 'start the web server'),
    ('show-news-from-jamendo', 'jamendo', 'print_new_tracks', 'show new tracks available at jamendo.com'),
    ('sms', 'sms', 'run_cli', 'send text messages (GSM)'),
    ('stream', 'stream', 'run_cli', 'handles stream events'),
    ('tags', 'tags', 'run_cli', 'interact with track metadata'),
    ('track', 'tracks', 'run_cli', 'works with individual tracks'),
    ('tsn', 'tsn', 'run', 'prepare and process a new So-So-News episode'),
    ('twit', 'twitter', 'run_cli', 'interacts with the twitter account'),
]

def find_command(command_name):
    for cmd, mod, fun, doc in COMMAND_MAP:
        if command_name == cmd:
            try:
                m = __import__('ardj.' + mod)
                m = getattr(m, mod)
                f = getattr(m, fun)
                return f
            except Exception, e:
                logging.error('Command "ardj %s" is broken: %s' % (cmd, e))


    if command_name is None:
        print 'Usage: ardj command\nAvailable commands:'
    else:
        print 'Unknown command: "%s", available commands:' % command_name

    maxlen = max([len(c[0]) for c in COMMAND_MAP])
    fmt = '  %%-%us   %%s' % maxlen
    for cmd, mod, fun, doc in sorted(COMMAND_MAP, key=lambda x: x[0]):
        print fmt % (cmd, doc)
    exit(1)


def run(args):
    ardj.log.install()
    if len(args) >= 2 and not args[1].startswith('-'):
        handler = find_command(args[1])
        if handler is not None:
            try:
                args = [a.decode('utf-8') for a in args[2:]]
                exit(handler(args))
            except KeyboardInterrupt:
                print 'Interrupted by user.'
                exit(1)
            except Exception, e:
                logging.error('ERROR handling command %s: %s' % (args[1], e) + traceback.format_exc(e))
                exit(1)
        logging.error('Unknown command: %s' % args[1])
        exit(1)

    find_command(None)
