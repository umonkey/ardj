# encoding=utf-8

"""ardj console.

Lets users communicate with the system using almost human language.  Used by
the jabber bot, a CLI is available."""

import os
import readline
import signal
import sys

import json

import ardj.database
import ardj.jabber
import ardj.listeners
import ardj.log
import ardj.settings
import ardj.speech
import ardj.tracks
import ardj.util


def is_user_admin(sender):
    return sender in ardj.settings.get('jabber/access', [])


def format_track_list(tracks, header=None):
    message = u''
    if header is not None:
        message += header.strip() + u'\n'
    for track in tracks:
        message += u'«%s» by %s — #%u ⚖%.2f ♺%s' % (track.get('title', 'untitled'), track.get('artist', 'unknown artist'), track.get('id', 0), track.get('weight', 0), track.get('count', '?'))
        if 'labels' in track:
            message += u' @' + u' @'.join(track['labels'])
        message += u'\n'
    return message


def get_ices_pid():
    pidfile = ardj.settings.get('jabber/ices_pid')
    if not pidfile:
        ardj.log.warning('The jabber/ices_pid file not set.')
        return None
    if not os.path.exists(pidfile):
        ardj.log.warning('%s does not exist.' % pidfile)
        return None
    return int(open(pidfile, 'rb').read().strip())


def signal_ices(sig):
    ices_pid = get_ices_pid()
    try:
        if ices_pid:
            os.kill(ices_pid, sig)
            ardj.log.debug('sent signal %s to process %s.' % (sig, ices_pid))
        else:
            ardj.util.run([ 'pkill', '-' + str(sig), 'ices.ardj' ])
            ardj.log.debug('sent signal %s to process %s using pkill (unsafe).' % (sig, ices_pid))
        return True
    except Exception, e:
        ardj.log.warning('could not kill(%u) ices: %s' % (sig, e))
        return False


def on_delete(args, sender, cur=None):
    if not args.isdigit():
        return 'Must specify a single numeric track id.'

    track = ardj.tracks.get_track_by_id(int(args), cur=cur)
    if not track:
        return 'No such track.'
    if not track.get('weight'):
        return 'This track was already deleted.'
    track['weight'] = 0
    ardj.tracks.update_track(track, cur=cur)
    return 'Deleted track %u.' % track['id']


def on_skip(args, sender, cur=None):
    if signal_ices(signal.SIGUSR1):
        return 'Request sent.'
    return 'Could not send the request for some reason.'


def on_restart(args, sender, cur=None):
    if args == 'ices':
        if signal_ices(signal.SIGTERM):
            ardj.util.run([ 'ices.ardj', '-B' ])
            return 'Done.'
        return 'Could not kill ices.ardj for some reason.'
    sys.exit(1)


def on_sql(args, sender, cur=None):
    if not args.endswith(';'):
        return 'SQL statements must end with a ;, for your own safety.'

    cur = cur or ardj.database.cursor()
    rows = cur.execute(args).fetchall()
    if not rows:
        return 'Empty result.'

    output = u'\n'.join([u'; '.join([unicode(cell) for cell in row]) for row in rows])
    return output


def on_twit(args, sender, cur=None):
    return ardj.twitter.send_message(args)


def on_speak(args, sender, cur=None):
    return ardj.speech.render_and_queue(args) or 'OK, please wait until the current song finishes playing.'


def on_echo(args, sender, cur=None):
    return args


def on_purge(args, sender, cur=None):
    ardj.tracks.purge()
    return 'OK'


def on_reload(args, sender, cur=None):
    if not signal_ices(signal.SIGHUP):
        return 'Failed.'
    return 'Ices will be reinitialized when track changes.'


def on_rocks(args, sender, cur=None):
    if args and not args.isdigit():
        return 'Usage: rocks [track_id]'

    track_id = args and int(args) or ardj.tracks.get_last_track_id(cur=cur)
    weight = ardj.tracks.add_vote(track_id, sender, 1, cur=cur)
    return 'OK, current weight of track #%u is %s.' % (track_id, weight)


def on_sucks(args, sender, cur=None):
    if args and not args.isdigit():
        return 'Usage: sucks [track_id]'

    track_id = args and int(args) or ardj.tracks.get_last_track_id(cur=cur)
    weight = ardj.tracks.add_vote(track_id, sender, -1, cur=cur)
    return 'OK, current weight of track #%u is %s.' % (track_id, weight)


def on_ban(args, sender, cur=None):
    if not args:
        return 'Usage: ban artist_name'
    cur = cur or ardj.database.cursor()
    count = cur.execute('SELECT COUNT(*) FROM tracks WHERE artist = ?', (args, )).fetchone()[0]
    if not count:
        return 'No tracks by this artist.'
    cur.execute('UPDATE tracks SET weight = 0 WHERE artist = ?', (args, ))
    return 'Deleted %u tracks.' % count


def on_shitlist(args, sender, cur=None):
    cur = cur or ardj.database.cursor()
    rows = cur.execute('SELECT id, artist, title, weight, count FROM tracks WHERE weight > 0 ORDER BY weight, title, artist LIMIT 10').fetchall()
    if not rows:
        return 'No tracks (database must be empty).'
    tracks = [{ 'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4] } for row in rows]
    return format_track_list(tracks, u'Lowest rated tracks:')


def on_hitlist(args, sender, cur=None):
    cur = cur or ardj.database.cursor()

    rows = cur.execute('SELECT id, artist, title, weight, count FROM tracks WHERE weight > 0 ORDER BY weight DESC, title, artist LIMIT 10').fetchall()
    if not rows:
        return 'No tracks (database must be empty).'
    tracks = [{ 'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4] } for row in rows]
    return format_track_list(tracks, u'Highest rated tracks:')


def on_queue(args, sender, cur=None):
    """Queue management.

    The 'queue flush' command removes tracks from queue (only those queued by
    the sender unless he's an admin).  Other arguments are search patterns for
    track artist/title, or label names if prefixed with @.

    If the user had not queued anything yet, a random jingle is added.  Jingles
    are marked with the "queue-jingle" label.  If the user is not an admin,
    he's not allowed to queue more than one track.
    """
    cur = cur or ardj.database.cursor()
    is_admin = is_user_admin(sender)

    if args == 'flush':
        if not is_admin:
            cur.execute('DELETE FROM queue WHERE owner = ?', (sender, ))
            return 'Removed your tracks from queue.'
        else:
            cur.execute('DELETE FROM queue')
            return 'Done.'

    elif args:
        tracks = ardj.tracks.find_ids(args, cur)[:1]
        have_tracks = cur.execute('SELECT COUNT(*) FROM queue WHERE owner = ?', (sender, )).fetchone()[0]

        if not is_admin:
            if have_tracks:
                return 'You have already queued a track, please wait.'

        if not tracks:
            return 'Could not find anything.'

        ardj.jabber.chat_say(u'%s requested track %s' % (sender.split('@')[0], u', '.join([ardj.tracks.identify(x) for x in tracks])))

        jingles = ardj.tracks.find_ids('-r @queue-jingle')[:1]
        if tracks and jingles and not have_tracks:
            tracks.insert(0, jingles[0])

        for track_id in tracks:
            ardj.tracks.queue(track_id, sender, cur)

    tracks = ardj.tracks.get_queue(cur)[:10]
    if not tracks:
        return 'Nothing is in the queue.'
    return format_track_list(tracks, u'Current queue:')


def on_find(args, sender, cur=None):
    cur = cur or ardj.database.cursor()
    tracks = [ardj.tracks.get_track_by_id(x, cur=cur) for x in ardj.tracks.find_ids(args, cur=cur)][:10]
    if not tracks:
        return 'Nothing was found.'
    return format_track_list(tracks, u'Found these tracks:')


def on_news(args, sender, cur=None):
    cur = cur or ardj.database.cursor()

    rows = cur.execute('SELECT id, artist, title, weight, count FROM tracks WHERE weight > 0 ORDER BY id DESC LIMIT 10').fetchall()
    if not rows:
        return 'No tracks at all.'
    tracks = [{ 'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3], 'count': row[4] } for row in rows]
    return format_track_list(tracks, 'Recently added tracks:')


def on_votes(args, sender, cur=None):
    cur = cur or ardj.database.cursor()

    if args.startswith('for '):
        track_id = int(args[4:].strip())
    else:
        track_id = ardj.tracks.get_last_track_id(cur)

    votes = cur.execute('SELECT email, vote FROM votes WHERE track_id = ?', (track_id, )).fetchall()
    if not votes:
        return 'No votes for that track.'

    pro = [row[0] for row in votes if row[1] > 0]
    contra = [row[0] for row in votes if row[1] < 0]
    return u'Pro: %s, contra: %s. ' % (', '.join(pro or ['nobody']), ', '.join(contra or ['nobody']))


def on_voters(args, sender, cur=None):
    cur = cur or ardj.database.cursor()
    rows = cur.execute('SELECT `email`, COUNT(*) AS `count` FROM `votes` GROUP BY `email` ORDER BY `count` DESC').fetchall()
    return u'Top voters: ' + u', '.join([u'%s (%u)' % (row[0], row[1]) for row in rows]) + u'.'


def on_play(args, sender, cur=None):
    cur = cur or ardj.database.cursor()
    if not args:
        current = ardj.tracks.get_urgent()
        if not current:
            return 'Playing everything.'
        return u'Current filter: %s' % u' '.join(current)
    ardj.tracks.set_urgent(args, cur=cur)
    return 'OK.'


def on_tags(args, sender, cur=None):
    if not args:
        return 'Usage: tags x, y, z for track_id'

    parts = args.split(' ')
    if len(parts) > 2 and parts[-2] == 'for':
        if not parts[-1].isdigit():
            return 'The last argument (track_id) must be an integer.'
        track_id = int(parts[-1])
        parts = parts[:-2]
    else:
        track_id = ardj.tracks.get_last_track_id(cur)

    labels = [l.strip(' ,@') for l in parts]
    current = ardj.tracks.add_labels(track_id, labels, owner=sender, cur=cur) or ['none']
    return u'New labels: %s.' % (u', '.join(sorted(current)))


def on_set(args, sender, cur=None):
    cur = cur or ardj.database.cursor()

    parts = args.split(' ')
    if not args or len(parts) < 3 or parts[1] != 'to':
        return 'Usage: set artist|title to value [for track_id]'

    if parts[0] not in ('artist', 'title'):
        return 'Unknown property: %s.' % parts[1]

    if len(parts) > 2 and parts[-2] == 'for':
        if not parts[-1].isdigit():
            return 'The last argument (track_id) must be an integer.'
        track_id = int(parts[-1])
        parts = parts[:-2]
    else:
        track_id = ardj.tracks.get_last_track_id(cur)

    track = ardj.tracks.get_track_by_id(track_id, cur)
    track[parts[0]] = u' '.join(parts[2:])
    ardj.tracks.update_track(track, cur=cur)

    return 'Done.'


def on_last(args, sender, cur=None):
    cur = cur or ardj.database.cursor()
    rows = cur.execute('SELECT t.id, t.artist, t.title, t.weight FROM tracks t INNER JOIN playlog l ON l.track_id = t.id ORDER BY l.ts DESC LIMIT 10')
    tracks = [{ 'id': row[0], 'artist': row[1], 'title': row[2], 'weight': row[3] } for row in rows]
    return format_track_list(tracks, 'Last played tracks:')


def on_dump(args, sender, cur=None):
    if not args or not args.isdigit():
        return 'Usage: dump track_id'

    cur = cur or ardj.database.cursor()

    track = ardj.tracks.get_track_by_id(int(args))
    if not track:
        return 'Track %s not found.' % args

    track['editable'] = is_user_admin(sender)

    votes = cur.execute('SELECT vote FROM votes WHERE track_id = ? AND email = ?', (track['id'], sender, )).fetchone()
    track['vote'] = votes and votes[0] or None

    return json.dumps(track, ensure_ascii=False)


def on_show(args, sender, cur=None):
    cur = cur or ardj.database.cursor()

    track_id = args and int(args) or ardj.tracks.get_last_track_id(cur)
    if not track_id:
        return 'Nothing is playing.'
    track = ardj.tracks.get_track_by_id(track_id, cur=cur)
    if not track:
        return 'Track %s not found.' % track_id

    result = u'«%s» by %s' % (track['title'], track['artist'])
    result += u'; id=%u weight=%.2f playcount=%u length=%s vote=%u last_played=%s. ' % (track['id'], track['weight'] or 0, track['count'] or 0, ardj.util.format_duration(int(track.get('length', 0))), ardj.tracks.get_vote(track['id'], sender), ardj.util.format_duration(track.get('last_played', 0), age=True))
    if track['labels']:
        result += u'Labels: ' + u', '.join(track['labels']) + u'. '
    return result.strip()


def on_status(args, sender, cur=None):
    cur = cur or ardj.database.cursor()

    track_id = ardj.tracks.get_last_track_id(cur=cur)
    if not track_id:
        return 'Silence.'

    track = ardj.tracks.get_track_by_id(track_id, cur=cur)
    if not track:
        return 'Playing an unknown track.'

    lcount = ardj.listeners.get_count()
    message = u'«%s» by %s — #%u ♺%u ⚖%.2f Σ%u' % (track.get('title', 'untitled'), track.get('artist', 'unknown artist'), track['id'], track.get('count', 0), track.get('weight', 0), lcount)
    if 'labels' in track:
        message += u' @' + u' @'.join(track['labels'])
    return message


def on_help(args, sender, cur=None):
    return get_usage(sender)


command_map = (
    ('ban', True, on_ban, 'deletes all tracks by the specified artist'),
    ('delete', True, on_delete, 'deletes the specified track'),
    ('dump', False, on_dump, 'shows track info in JSON'),
    ('echo', False, on_echo, 'sends back the message'),
    ('find', False, on_find, 'finds tracks matching a criteria'),
    ('help', False, on_help, 'shows this message'),
    ('hitlist', False, on_hitlist, 'shows 10 highest rated tracks'),
    ('last', False, on_last, 'shows last played tracks'),
    ('news', False, on_news, 'shows 10 recently added tracks'),
    ('play', True, on_play, 'set a custom playlist for 60 minutes'),
    ('purge', True, on_purge, 'cleans up the database'),
    ('queue', False, on_queue, 'queues tracks for playing'),
    ('reload', True, on_reload, 'asks ices to reconfigure'),
    ('restart', True, on_restart, 'restarts the bot or ices'),
    ('rocks', False, on_rocks, 'increases track weight'),
    ('set', True, on_set, 'changes track properties'),
    ('shitlist', False, on_shitlist, 'shows 10 lowest rated tracks'),
    ('show', False, on_show, 'shows basic track info'),
    ('skip', True, on_skip, 'skips current track'),
    ('speak', False, on_speak, 'asks a robot to say something'),
    ('sql', True, on_sql, 'runs a low-level database query'),
    ('status', False, on_status, 'shows what\'s being played now'),
    ('sucks', False, on_sucks, 'decreases track weight'),
    ('tags', True, on_tags, 'adds tags to a track'),
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
    public = ardj.settings.get('jabber/public_commands', None)
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


def process_command(text, sender=None, cur=None, quiet=False):
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

    cur = cur or ardj.database.cursor()

    sender = sender or 'console'
    is_admin = is_user_admin(sender)

    is_public_command = command in get_public_commands()
    if not is_public_command and not is_admin:
        ardj.log.info('CMD: %s: %s -- DENIED' % (sender, text), quiet=quiet)
        return 'You don\' have access to that command, sorry.  ' + get_usage(sender)

    for cmd_name, is_privileged, handler, description in command_map:
        if cmd_name == command.lower():
            ardj.log.info('CMD: %s: %s' % (sender, text), quiet=quiet)
            return handler(args.strip(), sender=sender, cur=cur)

    return 'Unknown command: %s.  %s' % (command, get_usage(sender))


def run_cli(args):
    sender = 'console'
    if args:
        sender = args[0]

    print 'Starting the interactive jabber-like CLI, press ^D to quit.'

    histfile = os.path.expanduser('~/.ardj_history')
    if os.path.exists(histfile):
        readline.read_history_file(histfile)

    while True:
        try:
            text = raw_input('command: ')
            if text:
                print process_command(text.decode('utf-8'), sender, quiet=True)
        except EOFError:
            readline.write_history_file(histfile)
            print '\nBye.'
            return
        except Exception, e:
            print >>sys.stderr, e
