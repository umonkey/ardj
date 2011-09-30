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
    """edit settings

    Opens the currently used config file in your preferred text editor."""
    import settings
    return settings.edit_cli(args)


def cmd_db(*args):
    """database functions

    Subcommands: console, flush-queue, mark-hitlist, mark-preshow, mark-recent,
    mark-orphans, mark-long, purge, stat, fix-artist-names.  By default opens
    the database console."""
    import database
    return database.run_cli(args)


def cmd_db_init(*args):
    """initializes the database

    Initializes the configured database by executing a set of preconfigured SQL
    instructions.  This is non-destructive.  You should run this after you
    install or upgrade ardj."""
    import database
    return database.cli_init(args)


def cmd_events(*args):
    """works with the upcoming events

    Interacts with the Last.fm event database.  Subcommands: refresh,
    update-website."""
    import tout
    return tout.run_cli(args)


def cmd_find_new_tracks(*args):
    """adds new songs from Last.fm

    See ardj.tracks.find_new_tracks() for details."""
    import tracks
    return tracks.find_new_tracks(args)


def cmd_hotline(*args):
    """work with the hotline

    Interacts with the hotline mailbox.  Subcommands: list, process.  See
    ardj.hotline.run_cli() for details."""
    import hotline
    return hotline.run_cli(args)


def cmd_icelog(*args):
    """work with icecast2 logs

    Subcommands: show-agents, add.  See the ardj.icelogger module for details."""
    import icelogger
    return icelogger.run_cli(args)


def cmd_jabber(*args):
    """run the jabber bot

    Controls the jabber bot.  Subcommands: run, run-child.  See the ardj.jabber
    module for details."""
    import jabber
    return jabber.run_cli(args)


def cmd_listeners(*args):
    """summarizes listeners.csv

    Subcommands: stats."""
    import listeners
    return listeners.run_cli(args)


def cmd_mail(*args):
    """send or receive mail

    Can be used to send mail or list incoming messages.  Subcommands: list,
    send.  See the ardj.mail module for details."""
    import mail
    return mail.run_cli(args)


def cmd_map_listeners(*args):
    """updates the listeners map

    Updates the listener map.  See ardj.map.update_listeners() for details."""
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
    """scan ReplayGain in files

    Calculates ReplayGain for all files which don't have these tags yet."""
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
