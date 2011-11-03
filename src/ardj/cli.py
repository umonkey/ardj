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


def cmd_console(*args):
    """opens a console for jabber commands"""
    from ardj import console
    console.run_cli(args)


def cmd_db_purge(*args):
    """deletes dead data from the database"""
    from ardj import database
    database.Open().purge()
    database.commit()


def cmd_db_console(*args):
    """opens the database console"""
    from ardj import database, util
    util.run(["sqlite3", "-header", database.Open().filename])


def cmd_db_init(*args):
    """initializes the database

    Initializes the configured database by executing a set of preconfigured SQL
    instructions.  This is non-destructive.  You should run this after you
    install or upgrade ardj."""
    import database
    return database.cli_init(args)


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
    """run the jabber bot"""
    from ardj import jabber
    jabber.Open(debug="--debug" in args).run()


def cmd_listeners(*args):
    """summarizes listeners.csv

    Subcommands: stats."""
    import listeners
    return listeners.run_cli(args)


def cmd_export_total_listeners(*args):
    """prints overall listening statistics to stdout (CSV)"""
    from ardj import listeners
    listeners.cli_total()


def cmd_export_yesterday_listeners(*args):
    """prints yesterday's listening statistics to stdout (CSV)"""
    from ardj import listeners
    listeners.cli_yesterday()


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
    """merge votes according to jabber aliases"""
    from ardj import database
    database.Open().merge_aliases()
    database.commit()


def cmd_say(*args):
    """renders text to voice using festival, then plays it"""
    import speech
    return speech.render_text_cli(args)


def cmd_scan_replaygain(*args):
    """calculate ReplayGain for tracks that don't have it"""
    from ardj import replaygain
    replaygain.run_cli(args)


def cmd_serve(*args):
    """start the web server"""
    import server
    return server.run_cli(args)


def cmd_show_news_from_jamendo(*args):
    """show new tracks available at jamendo.com"""
    import jamendo
    return jamendo.print_new_tracks(args)


def cmd_tags(*args):
    """display tags from files"""
    if not args:
        print "Files not specified."
        return False

    from ardj import tags
    for fn in args:
        if os.path.exists(fn):
            print "Tags in %s" % fn
            for k, v in sorted(tags.get(arg).items(), key=lambda x: x[0]):
                print '  %s = %s' % (k, v)


def cmd_track(*args):
    """works with individual tracks"""
    import tracks
    return tracks.run_cli(args)


def cmd_add_incoming_tracks(*args):
    """moves tracks from the incoming folder to the database"""
    from ardj import tracks
    files = tracks.find_incoming_files(delay=0, verbose=True)
    success = tracks.add_incoming_files(files)
    print "Added %u files to the database." % len(success)


def cmd_twit(msg, *args):
    """sends a message to twitter"""
    from ardj import twitter
    try:
        print twitter.send_message(msg)
    except twitter.ConfigError, e:
        print >> sys.stderr, e
        return False


def cmd_twit_replies(*args):
    """shows replies to your account"""
    from ardj import twitter
    try:
        for (name, text) in reversed(twitter.get_replies()):
            print '%s: %s' % (name, text)
    except twitter.ConfigError, e:
        print >> sys.stderr, e
        return False


def cmd_twit_replies_speak(*args):
    """render replies using festival and queue for playing"""
    from ardj import twitter
    try:
        replies = twitter.get_replies()
        if len(replies):
            nick, text = replies[0]
            print twitter.speak_message(nick, text.split(' ', 1)[1], play=True)
    except twitter.ConfigError, e:
        print >> sys.stderr, e
        return False


def cmd_update_schedule(*args):
    """looks for events in the Last.fm database"""
    from ardj import tout
    tout.update_schedule(refresh="--refresh" in args)


def cmd_update_track_weights(*args):
    """shift current weights to real weights"""
    from ardj import database, tracks
    tracks.update_real_track_weights()
    database.commit()


def cmd_update_track_lengths(*args):
    """update track lengths from files (maintenance)"""
    from ardj import tracks
    tracks.update_track_lengths()


def cmd_xmpp_send(*args):
    """send a Jabber message"""
    if len(args) < 2:
        print "Usage: ardj xmpp-send \"message text\" [recipient_jid]"
        exit(1)

    recipient = None
    if len(args) >= 3:
        recipient = args[2]

    from database import Message, commit
    Message.create(args[1], recipient)
    commit()


def cmd_download_artist(*args):
    """queues retrieving more tracks by the specified artists"""
    from ardj.database import ArtistDownloadRequest, commit
    for arg in args[1:]:
        if ArtistDownloadRequest.find_by_artist(arg) is None:
            ArtistDownloadRequest.create(arg, "nobody")
    commit()


def cmd_db_stats(*args):
    """shows database statistics"""
    from ardj.database import Track

    count, length = 0, 0
    for track in Track.find_all():
        count += 1
        if track.length:
            length += track.length

    print "%u tracks, %.1f hours." % (count, length / 60 / 60)


def cmd_queue_flush(*args):
    """delete everything from the queue"""
    from ardj.database import Queue, commit
    for item in Queue.find_all():
        item.delete()
    commit()


def cmd_fix_artist_names(*args):
    """correct names according to Last.fm"""
    from ardj.scrobbler import LastFM
    from ardj.database import Track, commit

    cli = LastFM().authorize()
    if cli is None:
        print "Last.fm authentication failed."
        return False

    names = Track.get_artist_names()
    print "Correcting %u artists." % len(names)

    for name in names:
        new_name = cli.get_corrected_name(name)
        if new_name is not None and new_name != name:
            logging.info(u"Correcting artist name \"%s\" to \"%s\"" % (name, new_name))
            Track.rename_artist(name, new_name)

    commit()


def cmd_mark_hitlist(*args):
    """marks best tracks with the \"hitlist\" tag"""
    from ardj import database
    database.Open().mark_hitlist()
    database.commit()


def cmd_mark_liked_by(label, *jids):
    """applies a label to tracks liked by all specified jids"""
    import database
    import tracks
    count = tracks.add_label_to_tracks_liked_by(label, jids, "console")
    print "Found %u tracks." % count
    database.Open().commit()
    return True


def cmd_mark_long(*args):
    """marks long tracks with the "long" label"""
    from ardj import database
    database.Open().mark_long()
    database.commit()


def cmd_mark_orphans(*args):
    """marks tracks that don't belong to a playlist with the "orphan" label"""
    from ardj import database
    database.Open().mark_orphans()
    database.commit()


def cmd_mark_recent(*args):
    """marks 100 recently added tracks with the "recent" label"""
    from ardj import database
    database.Open().mark_recent_music()
    database.commit()


def cmd_play(*args):
    """sets urgent playlist for next hour"""
    from ardj import database, tracks
    tracks.set_urgent(" ".join(args).decode("utf-8"))
    database.commit()


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

    if "--zsh" in args:
        arguments = []
        for k, v in sorted(globals().items()):
            if k.startswith("cmd_"):
                name = k[4:].replace("_", "-")
                info = v.__doc__.split("\n")[0].replace("'", "\\`").replace("\"", "\\\"")
                arguments.append("%s\\:'%s'" % (name, info))
        lst = " ".join(arguments)
        print "#compdef ardj\n# generated by ardj --zsh\n_arguments \"1:Select command:((%s))\"" % lst
        exit(0)

    if len(args) >= 2:
        handler = find_handler(args[1])
        if handler is not None:
            try:
                if handler(*args[2:]):
                    exit(0)
            except KeyboardInterrupt:
                pass
            except Exception, e:
                logging.error('ERROR handling command %s: %s' % (args[1], e) + traceback.format_exc(e))
                print "ERROR: %s\n%s" % (e, traceback.format_exc(e))
            exit(1)

    cmd_help(*args)
    exit(1)
