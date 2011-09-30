"""ARDJ, an artificial DJ.

This module contains the command line interface.  It first initializes the log
file, then, depending on the command line arguments, loads and executes the
appropriate submodule.

Commands are passed to the ardj binary as the first argument.  Command handlers
are functions prefixed with "cmd_", which have dashes replaced with
underscores.  For example, command "merge-votes" is handled by the
cmd_merge_votes function.
"""

import logging
import os
import sys
import traceback

import ardj.log


def cmd_config(*args):
    """edit settings"""
    import settings
    return settings.edit_cli(args)


def cmd_db(*args):
    """database functions"""
    import database
    return database.run_cli(args)


def cmd_db_init(*args):
    """initializes the database"""
    import database
    return database.cli_init(args)


def cmd_events(*args):
    """works with the upcoming events"""
    import tout
    return tout.run_cli(args)


def cmd_find_new_tracks(*args):
    """adds new songs from Last.fm"""
    import tracks
    return tracks.find_new_tracks(args)


def cmd_hotline(*args):
    """work with the hotline"""
    import hotline
    return hotline.run_cli(args)


def cmd_icelog(*args):
    """work with Icecast logs"""
    import icelogger
    return icelogger.run_cli(args)


def cmd_jabber(*args):
    """run the jabber bot"""
    import jabber
    return jabber.run_cli(args)


def cmd_listeners(*args):
    """summarizes listeners.csv"""
    import listeners
    return listeners.run_cli(args)


def cmd_mail(*args):
    """send or receive mail"""
    import mail
    return mail.run_cli(args)


def cmd_map_listeners(*args):
    """updates the listeners map"""
    import map
    return map.update_listeners(args)


def cmd_merge_votes(*args):
    """merge votes according to jabber/aliases"""
    import database
    return database.merge_votes(args)


def cmd_news(*args):
    """updates news from echo.msk.ru"""
    import news
    return news.run_cli(args)


def cmd_rg(*args):
    """scan ReplayGain in files"""
    import replaygain
    return replaygain.run_cli(args)


def cmd_say(*args):
    """renders text to voice using festival, then plays it"""
    import speech
    return speech.render_text_cli(args)


def cmd_serve(*args):
    """start the web server"""
    import server
    return server.run_cli(args)


def cmd_show_news_from_jamendo(*args):
    """show new tracks available at jamendo.com"""
    import jamendo
    return jamendo.print_new_tracks(args)


def cmd_sms(*args):
    """send text messages (GSM)"""
    import sms
    return sms.run_cli(args)


def cmd_stream(*args):
    """handles stream events"""
    import stream
    return stream.run_cli(args)


def cmd_tags(*args):
    """interact with track metadata"""
    import tags
    return tags.run_cli(args)


def cmd_track(*args):
    """works with individual tracks"""
    import tracks
    return tracks.run_cli(args)


def cmd_tsn(*args):
    """prepare and process a new So-So-News episode"""
    import tsn
    return tsn.run(args)


def cmd_twit(*args):
    """interacts with the twitter account"""
    import twitter
    return twitter.run_cli(args)


def cmd_help(*args):
    """shows this help screen"""
    commands = []

    for k, v in globals().items():
        if k.startswith("cmd_"):
            command = k[4:].replace("_", "-")
            commands.append((command, getattr(v, "__doc__", "").split("\n")[0].strip()))

    length = max([len(x[0]) for x in commands])

    print "Usage: ardj command\nAvailable commands:"
    fmt = '  %%-%us   %%s' % length
    for cmd, doc in sorted(commands):
        print fmt % (cmd, doc)

    return False


def find_handler(name):
    """Finds the right command handler.

    The best handler is the one with the exactly matching name.  If that one
    does not exist, all command handlers starting wigh the specified string are
    selected.  If more than one exsits, an error message is displayed."""

    commands = globals()

    cmd_name = "cmd_" + name.replace("-", "_")
    if cmd_name in commands:
        return commands[cmd_name]

    similar = []
    for k, v in commands.items():
        if k.startswith(cmd_name):
            similar.append(v)

    if len(similar) == 1:
        return similar[0]

    return None


def run(args):
    """The main command line interface entry point.

    Initializes the log file then looks for the specified command handler and
    executes it.  If no command was given or no handler could be found,
    displays a help screen.
    
    Returns 1 (i.e., an error) if the handler returned either False or None,
    otherwise returns zero (clear)."""
    ardj.log.install()

    if len(args) >= 2:
        handler = find_handler(args[1])
        if handler is not None:
            try:
                if handler(*args[1:]):
                    exit(0)
            except KeyboardInterrupt:
                pass
            except Exception, e:
                logging.error('ERROR handling command %s: %s' % (args[1], e) + traceback.format_exc(e))
            exit(1)

    cmd_help(*args)
    exit(1)
