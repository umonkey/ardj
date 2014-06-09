"""ARDJ, an artificial DJ.

This module contains the command line interface.  It first initializes the log
file, then, depending on the command line arguments, loads and executes the
appropriate submodule.

Commands are passed to the ardj binary as the first argument.  Command handlers
are functions prefixed with "cmd_", which have dashes replaced with
underscores.  For example, command "merge-votes" is handled by the
cmd_merge_votes function.
"""

import glob
import logging
import os
import random
import sys
import time
import traceback

import ardj.log


def is_running_from_source():
    my_path = os.path.realpath(__file__)
    return my_path.startswith(os.path.expanduser("~/"))


def cmd_find_new_tracks(*args):
    """adds new songs from Last.fm

    See ardj.tracks.find_new_tracks() for details."""
    import tracks
    return tracks.find_new_tracks(args)


def cmd_find_new_files(*args):
    """looks for new files in the media folder"""
    import tracks
    count = tracks.MediaFolderScanner().run()
    print "Found %u new files." % count
    return True


def cmd_jabber(*args):
    """run the jabber bot"""
    from ardj import jabber, settings
    bot = jabber.Open(debug="--debug" in args)
    if bot is not None:
        bot.run()


def cmd_export_total_listeners(*args):
    """prints overall listening statistics to stdout (CSV)"""
    from ardj import listeners
    listeners.cli_total()


def cmd_export_yesterday_listeners(*args):
    """prints yesterday's listening statistics to stdout (CSV)"""
    from ardj import listeners
    listeners.cli_yesterday()


def cmd_map_listeners(*args):
    """updates the listeners map

    Updates the listener map.  See ardj.map.update_listeners() for details."""
    import map
    return map.update_listeners(args)


def cmd_merge_votes(*args):
    """merge votes according to jabber aliases"""
    from ardj import users
    users.merge_aliased_votes()


def cmd_say(*args):
    """renders text to voice using festival, then plays it"""
    import speech
    return speech.render_text_cli(args)


def cmd_scan_replaygain(*args):
    """calculate ReplayGain for tracks that don't have it"""
    from ardj import replaygain
    replaygain.run_cli(args)


def cmd_serve(*args):
    """start all subprograms, run the radio"""
    from ardj import monitor
    return monitor.run_cli(args)


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


def cmd_print_current_track(*args):
    """prints the currently playing track"""
    from ardj import tracks
    import json
    print json.dumps(tracks.Track.get_last())


def cmd_twit(msg, *args):
    """sends a message to twitter"""
    from ardj import twitter
    try:
        print twitter.send_message(msg.decode("utf-8"))
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
    from ardj import database, tout
    tout.update_schedule(refresh="--refresh" in args)
    database.commit()


def cmd_xmpp_send(*args):
    """send a Jabber message"""
    if len(args) < 1:
        print "Usage: ardj xmpp-send \"message text\" [recipient_jid]"
        exit(1)

    recipient = None
    if len(args) > 1:
        recipient = args[1].decode("utf-8")

    from database import Message, commit
    Message(message=args[0].decode("utf-8"), re=recipient).put()
    commit()


def cmd_download_artist_schedule(*args):
    """queues retrieving more tracks by the specified artists"""
    from ardj.database import DownloadRequest, commit
    for arg in args[1:]:
        if DownloadRequest.find_by_artist(arg) is None:
            DownloadRequest(artist=arg, owner="console").put()
    commit()


def cmd_download_artist(*args):
    """downloads songs by an artist (immediately)"""
    from ardj.tracks import find_new_tracks
    find_new_tracks(args)


def cmd_queue_flush(*args):
    """delete everything from the queue"""
    from ardj.database import Queue, commit
    Queue.delete_all()
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
            logging.info("Correcting artist name \"%s\" to \"%s\"" % (name.encode("utf-8"), new_name.encode("utf-8")))
            Track.rename_artist(name, new_name)

    commit()


def cmd_lastfm_track_tags(artist_name, track_title):
    """show track tags from last.fm

    Usage: lastfm-track-tags "artist name" "track title"
    """
    from ardj.scrobbler import LastFM

    cli = LastFM()
    print u", ".join(cli.get_track_tags(artist_name.decode("utf-8"), track_title.decode("utf-8")))


def cmd_lastfm_find_tags(*args):
    """Adds lastfm:* tags to tracks that don't have them."""
    from ardj.tracks import add_missing_lastfm_tags
    add_missing_lastfm_tags()


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
    from ardj.tracks import mark_long
    print "Average length: %s, total long tracks: %u." % mark_long()


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
    if "UPSTART_JOB" in os.environ:
        ardj.log.install(os.environ["UPSTART_JOB"])
    else:
        ardj.log.install("ardj-cli")

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

    # Strip global modifiers.
    while len(args) > 1 and args[1].startswith("-"):
        del args[1]

    if len(args) >= 2:
        handler = find_handler(args[1])
        if handler is not None:
            try:
                if handler(*args[2:]) in (None, True):
                    exit(0)
            except KeyboardInterrupt:
                pass
            except Exception, e:
                ardj.log.log_error('ERROR handling command %s: %s' % (args[1], e), e)
                print "ERROR: %s" % e
                print traceback.format_exc(e)
            exit(1)

    cmd_help(*args)
    exit(1)
