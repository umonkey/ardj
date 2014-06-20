# encoding=utf-8

"""ardj console.

Lets users communicate with the system using almost human language.  Used by
the jabber bot, a CLI is available."""

import logging
import os
import re
import readline
import shlex
import signal
import sys
import traceback

import json

import ardj.database
import ardj.jabber
import ardj.listeners
import ardj.settings
try:
    import ardj.sound_menu
except:
    pass
import ardj.speech
import ardj.tracks
import ardj.users
import ardj.util


def is_user_admin(sender, safe=False):
    """Checks whether the user has special privileges."""
    return ardj.users.resolve_alias(sender) in ardj.users.get_admins()


def shortname(sender):
    return sender.split("@")[0]


def filter_labels(labels):
    """
    Returns only visible labels.

    Some labels contain a colon, like bookmarks (bm:alice@example.com), these
    labels should not be public.
    """
    return sorted(list(set([l for l in labels if ':' not in l])))


def format_track_list(tracks, header=None):
    message = u''
    if header is not None:
        message += header.strip() + u'\n'
    for track in tracks:
        if track is None:
            message += u'-- pause --\n'
        else:
            message += u"«{title}» by {artist} — [{id}] ⚖{weight:2} ♺{count}".format(
                id=track.get('id', 0),
                artist=track.get('artist', 'unknown artist'),
                title=track.get('title', 'untitled'),
                weight=float(track.get('weight') or 0),
                count=track.get('count') or 0,
            )
            if 'labels' in track:
                message += u' #' + u' #'.join(filter_labels(track['labels']))
            message += u'\n'
    return message


def sorted_tags(tags):
    return sorted(tags, key=lambda l: (":" in l, l.lower()))


def on_delete(args, sender):
    if not args.isdigit():
        return 'Must specify a single numeric track id.'

    track = ardj.tracks.get_track_by_id(int(args))
    if not track:
        return 'No such track.'
    if not track.get('weight'):
        return 'This track was already deleted.'
    track['weight'] = 0
    ardj.tracks.update_track(track)
    return 'Deleted track %u.' % track['id']


def on_skip(args, sender):
    def get_current_track():
        track_id = ardj.tracks.get_last_track_id()
        if track_id:
            track = ardj.tracks.get_track_by_id(track_id)
            return track

    sender_name = sender.split("@")[0]

    track = get_current_track()
    if track:
        message = u"%s skipped track %u: \"%s\" by %s" % (sender_name, track["id"], track["title"], track["artist"])
    else:
        message = u"%s skipped an unknown track." % sender_name

    try:
        if ardj.util.skip_current_track():
            ardj.jabber.chat_say(message)
            return 'Request sent.'
    except Exception, e:
        return str(e)

    return 'Could not send a skip request.  Details can be found in the log file.'


def on_say(args, sender):
    ardj.jabber.chat_say(args)
    return 'OK'


def on_restart(args, sender):
    sys.exit(1)


def on_sql(args, sender):
    """performs an SQL query, prints the result"""

    if not args.strip():
        return u"This command lets you perform a low-level SQL query and see the results, e.g.: sql SELECT COUNT(*) FROM tracks;"

    if not args.endswith(';'):
        return 'SQL statements must end with a ;, for your own safety.'

    if not args.lower().startswith("select"):
        return u"%u rows affected." % ardj.database.execute(args)

    rows = ardj.database.fetch(args)
    if not rows:
        return 'Nothing.'

    output = u'\n'.join([u'; '.join([unicode(cell) for cell in row]) for row in rows])
    return output


def on_twit(args, sender):
    try:
        from ardj import twitter
        return twitter.send_message(args)
    except Exception, e:
        return "Could not twit: %s" % e


def on_speak(args, sender):
    return ardj.speech.render_and_queue(args) or 'OK, please wait until the current song finishes playing.'


def on_echo(args, sender):
    if not args.strip():
        args = "I'm here.  This command can be used for testing the connection.  I'll send back whatever arguments you pass with it, e.g.: echo hello."
    return args


def on_purge(args, sender):
    ardj.tracks.purge()
    return 'OK'


def on_reload(args, sender):
    ardj.settings.load(True)
    return 'Reloaded the configuration file.'


def on_rocks(args, sender):
    if args and not args.isdigit():
        return 'Usage: rocks [track_id]'

    track_id = args and int(args) or ardj.tracks.get_last_track_id()
    weight = ardj.tracks.add_vote(track_id, sender, 1)
    if weight is None:
        return 'No such track.'
    return 'OK, current weight of track #%u is %.04f.' % (track_id, weight)


def on_sucks(args, sender):
    if args and not args.isdigit():
        return 'Usage: sucks [track_id]'

    track_id = args and int(args) or ardj.tracks.get_last_track_id()
    weight = ardj.tracks.add_vote(track_id, sender, -1)
    if weight is None:
        return 'No such track.'
    return 'OK, current weight of track #%u is %.04f.' % (track_id, weight)


def on_ban(args, sender):
    if not args:
        return 'Usage: ban artist_name'
    count = ardj.database.fetchone('SELECT COUNT(*) FROM tracks WHERE artist = ? AND weight > 0', (args, ))[0]
    if not count:
        return 'No tracks by this artist.'
    ardj.database.execute('UPDATE tracks SET weight = 0 WHERE artist = ?', (args, ))
    ardj.jabber.chat_say(u"%s deleted all %u tracks by %s." % (shortname(sender), count, args))
    return 'Deleted %u tracks.' % count


def on_shitlist(args, sender):
    rows = ardj.database.fetch('SELECT id, artist, title, weight, count FROM tracks WHERE weight > 0 ORDER BY weight, title, artist LIMIT 10')
    if not rows:
        return 'No tracks (database must be empty).'
    tracks = [{'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4]} for row in rows]
    return format_track_list(tracks, u'Lowest rated tracks:')


def on_hitlist(args, sender):
    rows = ardj.database.fetch('SELECT id, artist, title, weight, count FROM tracks WHERE weight > 0 ORDER BY weight DESC, title, artist LIMIT 10')
    if not rows:
        return 'No tracks (database must be empty).'
    tracks = [{'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4]} for row in rows]
    return format_track_list(tracks, u'Highest rated tracks:')


def on_queue(args, sender):
    """Queue management.  Adds the first matching track to the playback queue.  Usage:

    queue something -- queues the first track shown by "find something";
    queue flush -- removes your tracks from the queue;
    queue flush -a -- removes all tracks (admin only);
    queue -s -- disables the preroll (admin only);
    queue -d -- deletes the track from queue (must be yours);

    If the user had not queued anything yet, a random jingle is added.  Jingles
    are marked with the "queue-jingle" label.  If the user is not an admin,
    he's not allowed to queue more than one track.
    """
    is_admin = is_user_admin(sender)

    if args == 'flush':
        ardj.database.execute('DELETE FROM queue WHERE owner = ?', (sender, ))
        return 'Removed your tracks from queue.'

    if args == 'flush -a' and is_admin:
        ardj.database.execute('DELETE FROM queue')
        return 'Done.'

    elif args:
        silent = args.startswith('-s ')
        if silent:
            args = args[3:]

        delete = args.startswith('-d ')
        if delete:
            args = args[3:]

        tracks = ardj.tracks.find_ids(args, sender)

        if delete:
            for track_id in tracks:
                ardj.database.execute('DELETE FROM queue WHERE owner = ? AND track_id = ?', (sender, track_id, ))
            return 'Done.'

        tracks = tracks[:1]
        have_tracks = ardj.database.fetchone('SELECT COUNT(*) FROM queue WHERE owner = ?', (sender, ))[0]

        if not is_admin:
            silent = False
            if have_tracks:
                return 'You have already queued a track, please wait.'

        if not tracks:
            return 'Could not find anything.'

        ardj.jabber.chat_say(u'%s requested track %s' % (sender.split('@')[0], u', '.join([ardj.tracks.identify(x, unknown='(a pause)') for x in tracks])))

        jingles = ardj.tracks.find_ids('-r @queue-jingle')[:1]
        if tracks and jingles and not have_tracks and not silent:
            tracks.insert(0, jingles[0])

        for track_id in tracks:
            ardj.tracks.queue(track_id, sender)

    tracks = ardj.tracks.get_queue()[:10]
    if not tracks:
        return 'Nothing is in the queue.'
    return format_track_list(tracks, u'Current queue:')


def on_find(args, sender):
    """Finds tracks that match a query.  Has two modes of search:

    find something -- finds tracks with "something" in artist name or title;
    find @something -- finds tracks with the "something" label.

    By default results are sorted by rating, highest rated go first.  You can
    change this behaviour using the following modifiers:

    find -b           -- shows your bookmarked tracks, see "bm";
    find -r something -- show in random order;
    find -l something -- show newest first;
    find -s something -- show olders first.
    """
    all_tracks = ardj.tracks.find_ids(args, sender)
    tracks = [ardj.tracks.get_track_by_id(x) for x in all_tracks[:10]]
    if not tracks:
        return 'Nothing was found.'
    if len(all_tracks) > len(tracks):
        header = u'Found %u tracks, showing %u:' % (len(all_tracks), len(tracks))
    else:
        header = u'Found only these tracks:'
    return format_track_list(tracks, header)


def on_news(args, sender):
    rows = ardj.database.fetch('SELECT id, artist, title, weight, count FROM tracks WHERE weight > 0 ORDER BY id DESC LIMIT 10')
    if not rows:
        return 'No tracks at all.'
    tracks = [{'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4]} for row in rows]
    return format_track_list(tracks, 'Recently added tracks:')


def on_votes(args, sender):
    if args.startswith('for '):
        track_id = int(args[4:].strip())
    else:
        track_id = ardj.tracks.get_last_track_id()

    votes = ardj.tracks.get_track_votes(track_id)
    if not votes:
        return 'No votes for that track.'

    pro = [e for e, v in votes.items() if v > 0]
    contra = [e for e, v in votes.items() if v < 0]
    return u'Pro: %s, contra: %s. ' % (', '.join(pro or ['nobody']), ', '.join(contra or ['nobody']))


def on_voters(args, sender):
    voters = ardj.users.get_voters()
    if not voters:
        return u"There are no votes yet."

    output = u'Top voters:'
    for email, count, weight in voters:
        output += u'\n%s (%u, %.02f)' % (email, count, weight or 0)
    return output


def on_play(args, sender):
    """Set tags to select music by, instead of defined playlists.

    By default the specified tags will work for 30 minutes, unless
    different duration is specified with --time=MINUTES.

    Example: play --time=3600 tagme"""
    if not args:
        current = ardj.tracks.get_urgent()
        if not current:
            return 'Playing everything.'
        return u'Current filter: %s' % u' '.join(current)
    ardj.tracks.set_urgent(args)
    ardj.database.commit()
    return 'OK.'


def on_tags(args, sender):
    """Shows or modifies tags.

    tags add -remove [for track_id[,track_id,...]] -- manipulate tags
    tags add -remove --artist=\"Some Artist\"
    tags add -remove --filename=\"%some/path%\"
    tags -- show the tag cloud.
    """
    if not args or args == '-a':
        data = ardj.database.fetch('SELECT l.label, COUNT(*) AS count FROM labels l '
            'INNER JOIN tracks t ON t.id = l.track_id '
            'WHERE t.weight > 0 GROUP BY label ORDER BY l.label')
        if args != '-a':
            data = [x for x in data if ':' not in x[0]]
        if not data:
            return "There are no tags at all. Tag some tracks first."
        output = u', '.join([u'%s (%u)' % (l, c) for l, c in data]) + u'.'
        return output

    if not is_user_admin(sender):
        return 'Only admins can edit tags.'

    parts = shlex.split(args)

    if len(parts) > 2 and parts[-2] == 'for':
        if not re.match("^\d+(,\d+)*$", parts[-1]):
            return 'The last argument (track_id) must be a comma-separated list of integers.'
        track_ids = [int(i) for i in parts[-1].split(",")]
        parts = parts[:-2]

    elif "--artist=" in args:
        new_parts = []
        for part in parts:
            if part.startswith("--artist="):
                track_ids = ardj.tracks.find_by_artist(part[9:])
            else:
                new_parts.append(part)
        parts = new_parts

    elif "--filename=" in args:
        new_parts = []
        for part in parts:
            if part.startswith("--filename="):
                pattern = part.split("=", 1)[1]
                track_ids = ardj.tracks.find_by_filename(pattern)
            else:
                new_parts.append(part)
        parts = new_parts

    else:
        track_ids = [ardj.tracks.get_last_track_id()]

    labels = [l.strip(' ,@') for l in parts]
    if not labels:
        return "You forgot to specify which labels to add or remove."

    for track_id in track_ids:
        current = ardj.tracks.add_labels(track_id, labels, owner=sender) or ['none']

    if len(track_ids) == 1:
        return u'New labels: %s.' % (u', '.join(sorted_tags(current)))
    else:
        return "Tags modified for %u tracks." % len(track_ids)


def on_set(args, sender):
    parts = args.split(' ')
    if not args or len(parts) < 3 or parts[1] != 'to':
        return 'Usage: set artist|title|image|download to value [for track_id]'

    if parts[0] not in ('artist', 'title', 'image', 'download'):
        return 'Unknown property: %s.' % parts[1]

    if len(parts) > 2 and parts[-2] == 'for':
        if not parts[-1].isdigit():
            return 'The last argument (track_id) must be an integer.'
        track_id = int(parts[-1])
        parts = parts[:-2]
    else:
        track_id = ardj.tracks.get_last_track_id()

    track = ardj.tracks.get_track_by_id(track_id)
    track[parts[0]] = u' '.join(parts[2:])
    ardj.tracks.update_track(track)

    return 'Done.'


def on_last(args, sender):
    rows = ardj.database.fetch('SELECT t.id, t.artist, t.title, t.weight, t.count FROM tracks t INNER JOIN playlog l ON l.track_id = t.id ORDER BY l.ts DESC LIMIT 10')
    tracks = [{'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4]} for row in rows]
    return format_track_list(tracks, 'Last played tracks:')


def on_dump(args, sender):
    if not args or not args.isdigit():
        return 'Usage: dump track_id'

    track = ardj.tracks.get_track_by_id(int(args))
    if not track:
        return 'Track %s not found.' % args

    track['editable'] = is_user_admin(sender)

    votes = ardj.database.fetchone('SELECT vote FROM votes WHERE track_id = ? AND email = ?', (track['id'], sender, ))
    track['vote'] = votes and votes[0] or None

    if not track["download"]:
        base_url = ardj.settings.get('database/base_files_url')
        if base_url:
            track['download'] = base_url + track['filename']

    return json.dumps(track, ensure_ascii=False)


def on_show(args, sender):
    track_id = args and int(args) or ardj.tracks.get_last_track_id()
    if not track_id:
        return 'Nothing is playing.'
    track = ardj.tracks.get_track_by_id(track_id)
    if not track:
        return 'Track %s not found.' % track_id

    result = u'«%s» by %s' % (track['title'], track['artist'])
    result += u'; id=%u weight=%.2f playcount=%u length=%s vote=%u' % (track['id'], track['weight'] or 0, track['count'] or 0, ardj.util.format_duration(int(track.get('length', 0))), ardj.tracks.get_vote(track['id'], sender))
    if track.get("last_played"):
        result += u" last_played=%s" % ardj.util.format_duration(track['last_played'], age=True)
    result += ". "

    if track['labels']:
        result += u'Labels: ' + u', '.join(sorted_tags(list(set(track['labels'])))) + u'. '
    return result.strip()


def on_status(args, sender):
    track_id = ardj.tracks.get_last_track_id()
    if not track_id:
        return 'Silence.'

    track = ardj.tracks.get_track_by_id(track_id)
    if not track:
        return 'Playing an unknown track.'

    lcount = ardj.listeners.get_count() or 0
    title = track.get("title", "untitled")
    artist = track.get("artist", "unknown artist")
    count = track.get("count") or 0
    weight = track.get("weight") or 0

    message = u'«%s» by %s — [%u] ♺%u ⚖%.2f Σ%u' % (title, artist, track['id'], count, weight, lcount)
    if 'labels' in track:
        message += u' #' + u' #'.join(filter_labels(track['labels']))
    return message


def on_merge(args, sender):
    """Merges two tracks.  Usage: merge dst_id src_id.

    Track 2 is deleted, labels, votes and playcounts are moved to track 1.
    """
    ids = args.split(' ')
    if len(ids) != 2 or not ids[0].isdigit() or not ids[1].isdigit():
        return 'Usage: merge dst_id src_id'
    ardj.tracks.merge(int(ids[0]), int(ids[1]))
    return 'OK.'


def on_download(args, sender):
    """Finds free tracks by the specified artsit in Last.fm or Jamendo and downloads some."""
    if not args:
        return 'Usage: download artist'
    return ardj.tracks.schedule_download(args, sender)


def on_admins(args, sender):
    """Lists current admins."""
    admins = [ardj.users.resolve_alias(u) for u in ardj.users.get_admins()]
    admins = sorted(list(set(admins)))
    return u"Current admins: %s." % u", ".join(admins)


def on_bookmark(args, sender):
    """Adds a track to bookmarks.  If track id is not specified, the currently
    played track is bookmarked.  Latest bookmarks are shown afterwards."""
    track_ids = []
    remove = False
    for arg in [a.strip() for a in args.split(' ') if a.strip()]:
        if arg.isdigit():
            track_ids.append(int(arg))
        elif arg == '-d':
            remove = True
        else:
            raise Exception('Usage: bm [-d] track_ids...')
    if not track_ids:
        track_ids.append(ardj.tracks.get_last_track_id())

    ardj.tracks.bookmark(track_ids, sender, remove=remove)
    return 'Bookmark %s. Use "find -b" or "queue -b" to access yout bookmarks.' % (remove and 'removed' or 'added')


def on_help(args, sender):
    if not args:
        return get_usage(sender)
    for cmd_name, is_privileged, handler, description in command_map:
        if cmd_name == args.lower():
            doc = handler.__doc__
            if not doc:
                return 'No help on that command.'
            return doc.replace('    ', '').strip()
    return 'What? No such command: %s, try "help".' % args


command_map = (
    ('admins', False, on_admins, 'lists current admins'),
    ('ban', True, on_ban, 'deletes all tracks by the specified artist'),
    ('bm', False, on_bookmark, 'bookmark tracks (accepts optional id)'),
    ('delete', True, on_delete, 'deletes the specified track'),
    ('dump', False, on_dump, 'shows track info in JSON'),
    ('download', False, on_download, 'download new music from last.fm and jamendo'),
    ('echo', False, on_echo, 'sends back the message'),
    ('find', False, on_find, 'finds tracks matching a criteria'),
    ('help', False, on_help, 'shows this message'),
    ('hitlist', False, on_hitlist, 'shows 10 highest rated tracks'),
    ('last', False, on_last, 'shows last played tracks'),
    ('merge', True, on_merge, 'merges two tracks'),
    ('news', False, on_news, 'shows 10 recently added tracks'),
    ('play', True, on_play, 'set a custom playlist for 60 minutes'),
    ('purge', True, on_purge, 'cleans up the database'),
    ('queue', False, on_queue, 'queues tracks for playing'),
    ('restart', True, on_restart, 'restarts the bot'),
    ('rocks', False, on_rocks, 'increases track weight'),
    ('say', True, on_say, 'sends a message to the chat room'),
    ('set', True, on_set, 'changes track properties'),
    ('shitlist', False, on_shitlist, 'shows 10 lowest rated tracks'),
    ('show', False, on_show, 'shows basic track info'),
    ('skip', True, on_skip, 'skips current track'),
    ('speak', False, on_speak, 'asks a robot to say something'),
    ('sql', True, on_sql, 'runs a low-level database query'),
    ('status', False, on_status, 'shows what\'s being played now'),
    ('sucks', False, on_sucks, 'decreases track weight'),
    ('tags', False, on_tags, 'see tag cloud, edit track tags (admins only)'),
    ('twit', True, on_twit, 'sends a message to Twitter'),
    ('voters', True, on_voters, 'shows all voters'),
    ('votes', True, on_votes, 'shows who voted for a track'),
)

command_aliases = {
    u'кщслы': 'rocks',
    u'ыгслы': 'sucks',
}


def get_public_commands():
    """Returns the list of commands available to anonymous users."""
    public = ardj.settings.get2('jabber/public_commands', "public_jabber_commands", None)
    if not public:
        public = [c[0] for c in command_map if not c[1]]
    return public


def get_usage(sender):
    """Describes available commands.

    Only describes commands that are available to that user."""
    is_admin = is_user_admin(sender)
    message = u"Available commands:\n"
    for name, is_privileged, handler, description in sorted(command_map, key=lambda c: c[0]):
        if not is_privileged:
            message += u'%s\t— %s\n' % (name, description)
    if is_admin:
        message += u'\nPrivileged commands:\n'
        for name, is_privileged, handler, description in sorted(command_map, key=lambda c: c[0]):
            if is_privileged:
                message += u'%s\t— %s\n' % (name, description)
    return message


def process_command(text, sender=None, quiet=False):
    """Processes one message, returns a text reply.

    Arguments:
    text -- the command, e.g. "show 123"
    sender -- sender's email address
    cur -- pass if you want a transaction
    """
    text = (text or '').strip()
    if ' ' in text:
        command, args = text.split(' ', 1)
    else:
        command, args = text, ''
    command = command_aliases.get(command.lower(), command.lower())

    logging.debug((u"%s: %s" % (sender or "unknown sender", text)).encode("utf-8"))

    sender = sender or 'console'
    is_admin = is_user_admin(sender)

    options = []
    for cmd_name, is_privileged, handler, description in command_map:
        if is_privileged and not is_admin:
            continue
        if cmd_name.startswith(command.lower()):
            options.append((cmd_name, handler))

    if not options:
        return 'What?  No such command: %s, see "help".' % command

    if len(options) > 1:
        return 'Did you mean %s?' % ardj.util.shortlist([o[0] for o in options], limit=1000, glue='or')

    return options[0][1](args.strip(), sender=sender)


def print_response(message):
    has_color = "color" in os.getenv("TERM", "")
    for line in message.rstrip().split("\n"):
        if has_color:
            line = "\033[92m" + line + "\033[m"
        print line.encode("utf-8")


def run_cli(args):
    if args:
        sender = args[0]
    elif "@" in os.getenv("MAIL", ""):
        sender = os.getenv("MAIL")
    else:
        sender = "console"

    print 'Starting the interactive jabber-like CLI, press ^D to quit.'
    print 'You are identified ad "%s".' % sender

    histfile = os.path.expanduser('~/.ardj_history')
    if os.path.exists(histfile):
        readline.read_history_file(histfile)

    if is_user_admin(sender):
        prompt = "ardj# "
    else:
        prompt = "ardj$ "

    while True:
        try:
            text = raw_input(prompt)
            if text:
                response = process_command(text.decode('utf-8'), sender, quiet=True)
                print_response(response)
                ardj.database.Open().commit()
        except EOFError:
            readline.write_history_file(histfile)
            print '\nBye.'
            return
        except Exception, e:
            print >> sys.stderr, e, traceback.format_exc(e)
