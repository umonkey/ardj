# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:

import math
import os
import re
import shutil # move()
import socket # for gethostname()
import subprocess
import sys
import time
import traceback
import urllib
from xml.sax import saxutils

from ardj.jabberbot import JabberBot, botcmd
from ardj.filebot import FileBot, FileNotAcceptable
from ardj import twitter
from ardj import xmpp
import notify
import tags

def log(msg):
    print >>sys.stderr, msg

class MyFileReceivingBot(FileBot):
    def is_file_acceptable(self, sender, filename, filesize):
        if not self.check_access(sender):
            log('Refusing to accept files from %s.' % sender)
            raise FileNotAcceptable('I\'m not allowed to receive files from you, sorry.')
        if os.path.splitext(filename.lower())[1] not in ['.mp3', '.ogg']:
            raise FileNotAcceptable('I only accept MP3 and OGG files, which "%s" doesn\'t look like.' % os.path.basename(filename))

    def callback_file(self, sender, filename):
        dst_path = os.path.join(self.ardj.config.get_music_dir(), 'incoming', sender.split('/')[0])
        if not os.path.exists(dst_path):
            os.makedirs(dst_path)

        dst_name = self.add_filename_suffix(os.path.join(dst_path, os.path.basename(filename)))
        shutil.move(filename, dst_name)

        log('Received %s.' % dst_name)
        track_id = self.ardj.add_track_from_file(dst_name)

        return 'Your file was assigned number %u. Use the "news" command to see last added files, "set playlist to xyz for %u" to move this file from @incoming.' % (track_id, track_id)

    def add_filename_suffix(self, filename):
        """
        Makes sure that filename does not exist by addind a numeric index
        to the file's name if necessary.
        """
        source = filename
        index = 1
        while os.path.exists(filename):
            parts = os.path.splitext(source)
            filename = parts[0] + '_' + unicode(index) + parts[1]
            index += 1
        return filename

class ardjbot(MyFileReceivingBot):
    PROCESS_MSG_FROM_SELF = True
    PROCESS_MSG_FROM_UNSEEN = True

    PING_FREQUENCY = 60
    PING_TIMEOUT = 2

    def __init__(self, ardj):
        self.ardj = ardj
        self.twitter = None
        self.dbtracker = None
        self.lastping = None # время последнего пинга
        self.pidfile = '/tmp/ardj-jabber.pid'
        self.publicCommands = self.ardj.config.get('jabber/public-commands', 'help rocks sucks show last hitlist shitlist ping pong').split(' ')

        try:
            tmp = twitter.Api(username=ardj.config.get('twitter/consumer_key'),
                password=ardj.config.get('twitter/consumer_secret'),
                access_token_key=ardj.config.get('twitter/access_token_key'),
                access_token_secret=ardj.config.get('twitter/access_token_secret'))
            self.twitter = tmp
            log('Logged in to Twitter.')
        except: pass

        login, password = self.split_login(self.ardj.config.get('jabber/login'))
        resource = socket.gethostname() + '/' + str(os.getpid()) + '/'
        super(ardjbot, self).__init__(login, password, res=resource, debug=ardj.debug)

    def get_users(self):
        """
        Returns the list of authorized jids.
        """
        return self.ardj.config.get('jabber/access', [])

    def split_login(self, uri):
        name, password = uri.split('@', 1)[0].split(':', 1)
        host = uri.split('@', 1)[1]
        return (name + '@' + host, password)

    def idle_proc(self):
        """
        Sends a ping to self every PING_TIMEOUT/2 seconds.  If last reply was
        longer than PING_TIMEOUT seconds ago, a suicide is commited.
        """
        if time.time() - self.lastping > self.PING_FREQUENCY:
            self.lastping = time.time()
            log('Pinging the server.')
            ping = xmpp.Protocol('iq',typ='get',payload=[xmpp.Node('ping',attrs={'xmlns':'urn:xmpp:ping'})])
            res = self.conn.SendAndWaitForResponse(ping, self.PING_TIMEOUT)
            log('Got response: ' + str(res))
            if res is None:
                log('Terminating due to PING timeout.')
                self.quit(1)
        super(ardjbot, self).idle_proc()

    def on_connected(self):
        log('on_connected called.')
        self.lastping = time.time()
        self.dbtracker = notify.monitor([self.ardj.database.filename], self.on_file_changes)
        if self.pidfile:
            try:
                open(self.pidfile, 'w').write(str(os.getpid()))
            except IOError, e:
                print >>sys.stderr, 'Could not write to %s: %s' % (self.pidfile, e)
        self.update_status()

    def on_file_changes(self, action, path):
        try:
            if path == self.ardj.database.filename:
                if 'modified' == action:
                    return self.update_status()
        except IOError, e:
            log('IOError: %s, shutting down.' % e)
            self.quit(1)
        except Exception, e:
            log('Exception in inotify handler: %s' % e)
            traceback.print_exc()

    def shutdown(self):
        # self.on_disconnect() # called by JabberBot afterwards.
        log('shutdown: shutting down JabberBot.')
        JabberBot.shutdown(self)
        if self.pidfile and os.path.exists(self.pidfile):
            log('shutdown: removing the pid file.')
            os.unlink(self.pidfile)
        log('shutdown: over.')

    def update_status(self, onstart=False):
        """
        Updates the status with the current track name.
        Called by inotify, if available.
        """
        track = self.get_current_track()
        if track is not None:
            if self.ardj.config.get('jabber/status', False):
                if track.has_key('artist') and track.has_key('title'):
                    status = u'«%s» by %s' % (track['title'], track['artist'])
                else:
                    status = os.path.basename(track['filename'])
                status += u' — #%u @%s ♺%u ⚖%.2f' % (track['id'], track['playlist'], track['count'], track['weight'])
                self.status_message = status
            if self.ardj.config.get('jabber/tunes', True):
                self.send_tune(track)

    def get_current(self):
        """Возвращает имя проигрываемого файла из краткого лога."""
        return self.get_current_track()['filepath']

    def get_current_track(self):
        """
        Возвращает информацию о последней проигранной дорожке.
        """
        return self.ardj.get_last_track()

    def check_access(self, sender):
        return sender.split('/')[0] in self.get_users()

    def callback_message(self, conn, mess):
        """Extended message handler

        Adds an explicit database commit after all messages.
        """
        try:
            if mess.getType() == 'chat':
                body = mess.getBody()
                if body is not None:
                    is_public = body.strip().split(' ')[0] in self.publicCommands
                    if not is_public and not self.check_access(mess.getFrom().getStripped()):
                        log('Refusing access to %s.' % mess.getFrom())
                        return self.send_simple_reply(mess, 'Available commands: %s.' % ', '.join(self.publicCommands))
            return JabberBot.callback_message(self, conn, mess)
        finally:
            self.ardj.database.commit()

    @botcmd
    def set(self, message, args):
        "Modifies track properties"
        r = re.match('(\S+)\s+to\s+(.+)\s+for\s+(\d+)$', args)
        if r:
            a1, a2, a3 = r.groups()
            track = self.ardj.get_track_by_id(int(a3))
        else:
            r = re.match('(\S+)\s+to\s+(.+)$', args)
            if r:
                a1, a2 = r.groups()
                track = self.get_current_track()
            else:
                return u'Syntax: set prop to value [for id]'

        if a1 == 'labels' and a2:
            labels = re.split('[,\s]+', a2)
            result = self.ardj.database.add_labels(track['id'], message.getFrom().getStripped(), labels) or ['none']
            return u'Current labels for %s: %s.' % (self.get_linked_title(track), u', '.join(sorted(result)))

        types = { 'playlist': unicode, 'artist': unicode, 'title': unicode }
        if a1 not in types:
            return u'Unknown property: %s, available: %s.' % (a1, u', '.join(types.keys()))

        try:
            a2 = types[a1](a2)
        except Exception, e:
            return u'Wrong data type for property %s: %s' % (a1, e)

        old = track[a1]
        if old == a2:
            return u'That\'s the current value, yes.'

        track[a1] = a2
        self.ardj.update_track(track)

        log(u'%s changed %s from "%s" to "%s" for %s; #%u @%s' % (self.get_linked_sender(message), a1, old, a2, self.get_linked_title(track), track['id'], track['playlist']))

    @botcmd(hidden=True)
    def delete(self, message, args):
        "Deletes a track (sets weight to 0)\n\nUsage: delete track_id\n  or:\nUsage: delete from table where ...;"
        if args.lower().startswith('from'):
            if not args.endswith(';'):
                return u'SQL commands must end with a ; to prevent accidents.'
            self.ardj.database.cursor().execute(u'delete ' + args)
            return u'ok'
        track = args and self.ardj.get_track_by_id(int(args)) or self.get_current_track()
        if not track['weight']:
            return u'Zero weight already.'
        elif track['weight'] > 1:
            return u'This track is protected (weight=%f), use \'set weight to 0\' if you are sure.' % track['weight']
        old = track['weight']
        track['weight'] = 0
        self.ardj.update_track(track)
        log(u'%s changed weight from %s to 0 for %s; #%u @%s' % (self.get_linked_sender(message), old, self.get_linked_title(track), track['id'], track['playlist']))
        if not args:
            self.skip(message, args)

    @botcmd(hidden=True)
    def undelete(self, message, args):
        "Undeletes a track (sets weight to 1)"
        track = args and self.ardj.get_track_by_id(int(args)) or self.get_current_track()
        if track['weight']:
            return u'This track\'s weight is %s, not quite zero.' % (track['weight'])
        track['weight'] = 1.
        self.ardj.update_track(track)
        log(u'%s changed weight from 0 to 1 for %s; #%u @%s' % (self.get_linked_sender(message), self.get_linked_title(track), track['id'], track['playlist']))

    @botcmd
    def skip(self, message, args):
        "Skip to next track"
        try:
            self.send_signal('USR1', 'ices')
            return u'ok'
        except Exception, e:
            return unicode(e)

    @botcmd
    def last(self, message, args):
        "Show last 10 played tracks"
        rows = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks ORDER BY last_played DESC LIMIT 10').fetchall()]
        if not rows:
            return u'Nothing was played yet.'
        message = u'Last played tracks:'
        for row in rows:
            message += u'<br/>\n%s — @%s, #%u' % (self.get_linked_title(row), row['playlist'], row['id'])
        return message

    @botcmd
    def show(self, message, args):
        "Show detailed track info"
        args = self.split(args)
        if not args:
            track = self.get_current_track()
            if track is None:
                return 'Nothing is playing.'
        else:
            track = self.ardj.get_track_by_id(int(args[0]))
        if track is None:
            return u'No such track.'
        result = self.get_linked_title(track)
        result += u'; #%u @%s filename="%s" weight=%f playcount=%u length=%us' % (track['id'], track['playlist'], track['filename'], track['weight'], track['count'], track['length'])
        """
        result += u'. Tags:\n'
        tt = tags.get(track.path)
        for k in tt:
            result += u'%s: %s\n' % (k, tt[k])
        """
        return result.strip()

    @botcmd
    def say(self, message, args):
        "Send a message to all connected users"
        if len(args):
            self.broadcast(u'%s said: %s' % (self.get_linked_sender(message), args), True)

    @botcmd(hidden=True)
    def restart(self, message, args):
        "Shut down the bot (will be restarted)"
        self.quit(1)

    @botcmd(hidden=True)
    def select(self, message, args):
        "Low level access to the database"
        result = u''
        for row in self.ardj.database.cursor().execute(message.getBody()).fetchall():
            result += u', '.join([unicode(cell) for cell in row]) + u'\n<br/>'
        if not result:
            result = u'Nothing.'
        return result

    @botcmd(hidden=True)
    def update(self, message, args):
        "Low level update to the database"
        sql = 'update ' + args
        if not sql.endswith(';'):
            return u'SQL updates must end with a ; to prevent accidents.'
        self.ardj.database.cursor().execute(sql)
        log(u'SQL from %s: %s' % (self.get_linked_sender(message), sql))

    @botcmd
    def twit(self, message, args):
        "Send a message to Twitter"
        if not self.twitter:
            return u'Twitter is not enabled in the config file.'
        posting = self.twitter.PostUpdate(args.encode('utf-8'))
        url = 'http://twitter.com/' + posting.GetUser().GetScreenName() + '/status/' + str(posting.GetId())
        log(u'%s sent <a href="%s">a message</a> to twitter: %s' % (self.get_linked_sender(message), url, args))
        return url

    @botcmd
    def twits(self, message, args):
        "Show twitter replies"
        if not self.twitter:
            return u'Twitter is not enabled in the config file.'
        html = u''
        for reply in self.twitter.GetReplies():
            html += u'<a href="http://twitter.com/%s/status/%s">%s</a>: %s\n' % (reply.user.screen_name, reply.id, reply.user.screen_name, saxutils.escape(reply.text))
        for reply in self.twitter.FilterPublicTimeline('#tmradio'):
            html += u'<a href="http://twitter.com/%s/status/%s">%s</a>: %s\n' % (reply.user.screen_name, reply.id, reply.user.screen_name, saxutils.escape(reply.text))
        if not len(html):
            html = u'Nothing.'
        return html.replace('\n', '<br/>\n')

    @botcmd(hidden=True)
    def echo(self, message, args):
        "Send back the arguments"
        return args

    def split(self, args):
        if not args:
            return []
        return args.split(u' ')

    def run(self):
        return self.serve_forever(connect_callback=self.on_connected, disconnect_callback=self.on_disconnect)

    @botcmd(hidden=True)
    def purge(self, message, args):
        "Erase tracks with zero weight"
        cur = self.ardj.database.cursor()
        musicdir = self.ardj.config.get_music_dir()
        for id, filename in [(row[0], os.path.join(musicdir, row[1].encode('utf-8'))) for row in cur.execute('SELECT id, filename FROM tracks WHERE weight = 0').fetchall()]:
            if os.path.exists(filename):
                os.unlink(filename)
        cur.execute('DELETE FROM tracks WHERE weight = 0')
        return u'ok'

    @botcmd
    def sync(self, message, args):
        "Update database (finds new and dead files)"
        self.ardj.sync()
        return self.news(message, args)

    def get_linked_title(self, track):
        if not track['artist']:
            return track['filename']
        elif not track['title']:
            link = os.path.basename(track['filename'])
        else:
            link = u'«<a href="http://www.last.fm/music/%s/_/%s">%s</a>»' % (urllib.quote(track['artist'].strip().encode('utf-8')), urllib.quote(track['title'].strip().encode('utf-8')), saxutils.escape(track['title'].strip()))
        link += u' by <a href="http://www.last.fm/music/%s">%s</a>' % (urllib.quote(track['artist'].strip().encode('utf-8')), saxutils.escape(track['artist'].strip()))
        return link

    @botcmd
    def reload(self, message, args):
        "Reload ices config and playlist scripts"
        try:
            self.send_signal('HUP', 'ices')
            return u'Ices will be reinitialized when the track changes.'
        except Exception, e:
            return unicode(e)

    @botcmd(pattern='^(?:(\d+)\s+)?(?:rocks)$')
    def rocks(self, message, args):
        """Express your love for the current track
        
        Usage: "[track_id] rocks".  If the track id is not specified, the current track is assumed.
        """
        track = self.get_track(args, 0)
        if track is None:
            return 'Nothing is playing.'
        else:
            votes, weight = self.__vote(track['id'], message.getFrom().getStripped(), 1)
            return u'Recorded a vote for %s, weight: %s.' % (self.get_linked_title(track), weight)

    @botcmd(pattern='^(?:(\d+)\s+)?(?:sucks)$')
    def sucks(self, message, args):
        """Express your hate for the current track
        
        Usage: "[track_id] sucks".  If the track id is not specified, the current track is assumed.
        """
        track = self.get_track(args, 0)
        if track is None:
            return 'Nothing is playing.'
        else:
            votes, weight = self.__vote(track['id'], message.getFrom().getStripped(), -1)
            return u'Recorded a vote against %s weight: %s.' % (self.get_linked_title(track), weight)

    def get_track(self, args, index):
        if type(args) != tuple:
            raise TypeError("Use the 'help' command to understand how this works.")
        if args[index] is None:
            return self.ardj.get_last_track()
        elif str(args[index]).isdigit():
            return self.ardj.get_track_by_id(int(args[index]))
        raise TypeError("Track id must be an integer, or not specified at all.")

    @botcmd
    def shitlist(self, message, args):
        "List tracks with zero weight"
        tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks WHERE weight = 0 ORDER BY title, artist').fetchall()]
        if not tracks:
            return u'The shitlist is empty.'
        message = u'The shitlist has %u items:' % len(tracks)
        for track in tracks:
            message += u'\n<br/>%s — #%u @%s' % (self.get_linked_title(track), track['id'], track['playlist'])
        message += u'\n<br/>Use the "purge" command to erase these tracks.'
        return message

    @botcmd
    def hitlist(self, message, args):
        "Shows X top rated tracks"
        limit = args and int(args) or 10
        tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4], 'weight': row[5] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist, weight FROM tracks WHERE weight > 0 ORDER BY weight DESC LIMIT ' + str(limit)).fetchall()]
        if not tracks:
            return u'The hitlist is empty.'
        message = u'Top %u tracks:' % len(tracks)
        for track in tracks:
            message += u'\n<br/>  %s — #%u @%s %%%s' % (self.get_linked_title(track), track['id'], track['playlist'], track['weight'])
        return message

    @botcmd
    def queue(self, message, args):
        """Adds a track to queue\n\nUsage: queue [pattern]
        
        The pattern can be a track id or a part of its name, artist or
        filename.  If only one track matches, it's queued, otherwise an error
        is shown.
        """
        cur = self.ardj.database.cursor()

        # Если есть нецифровые элементы, выполняем поиск.
        if len(args.strip()):
            if len([x for x in args.split(' ') if not x.isdigit()]):
                rows = cur.execute('SELECT id FROM tracks WHERE title LIKE ? ORDER BY title', (u'%' + args + u'%', )).fetchall()
                if rows:
                    self.ardj.queue_track(int(rows[0][0]), cur)
                else:
                    return u'Ничего похожего нет.'
            elif args:
                for id in [x for x in args.split(' ') if x]:
                    self.ardj.queue_track(int(id), cur)
        tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4], 'qid': row[5] } for row in self.ardj.database.cursor().execute('SELECT t.id, t.filename, t.artist, t.title, t.playlist, q.id FROM tracks t INNER JOIN queue q ON q.track_id = t.id ORDER BY q.id').fetchall()]
        if not tracks:
            return u'Queue empty, use "queue track_id..." to fill.'
        message = u'Current queue:'
        for track in tracks:
            message += u'\n<br/>%u. %s — #%u @%s' % (track['qid'], self.get_linked_title(track), track['id'], track['playlist'])
        return message + u'\n<br/>Use "queue track_id..." to add more tracks and "find xyz" to find some ids.'

    @botcmd
    def find(self, mess, args):
        u"Finds a track\n\nUsage: find substring\nLists all tracks that contain this substring in the artist, track or file name. The substring can contain spaces. If you want to see more than 10 matching tracks, use the select command, e.g.: SELECT id, filename FROM tracks WHERE ..."
        if not args:
            return self.find.__doc__.split('\n\n')[1]
        like = '%' + args + '%'
        tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks WHERE title LIKE ? OR artist LIKE ? ORDER BY id LIMIT 10', (like, like, )).fetchall()]
        if not tracks:
            return u'No matching tracks.'
        message = u'Found %u tracks:' % len(tracks)
        for track in tracks:
            message += u'\n<br/>  %s — #%u @%s' % (self.get_linked_title(track), track['id'], track['playlist'])
        return message + u'\n<br/>You might want to use "queue track_ids..." now.'

    @botcmd
    def news(self, mess, args):
        u"Shows last added tracks"
        tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks ORDER BY id DESC LIMIT 10').fetchall()]
        if not tracks:
            return u'No news.'
        message = u'Last %u tracks:' % len(tracks)
        for track in tracks:
            message += u'\n<br/>  %s — #%u @%s' % (self.get_linked_title(track), track['id'], track['playlist'])
        return message

    @botcmd(pattern='^votes(?: for (\d+))?$')
    def votes(self, mess, args):
        """Shows votes for a track

        Usage: "votes [for track_id]".  If track_id is not specified, the last played track is assumed.
        """
        track = self.get_track(args, 0)
        if track is None:
            return u'Nothing is playing.'
        votes = self.ardj.database.cursor().execute('SELECT email, vote FROM votes WHERE track_id = ?', (track['id'], )).fetchall()
        pro = [row[0] for row in votes if row[1] > 0]
        if not pro:
            pro.append('nobody')
        contra = [row[0] for row in votes if row[1] < 0]
        if not contra:
            contra.append('nobody')
        return u'Pro: %s, contra: %s.' % (', '.join(pro), ', '.join(contra))

    @botcmd
    def voters(self, mess, args):
        u"Shows top voters."
        rows = self.ardj.database.cursor().execute('SELECT `email`, COUNT(*) AS `count` FROM `votes` GROUP BY `email` ORDER BY `count` DESC').fetchall()
        return u'Top voters: ' + u', '.join([u'%s (%u)' % (row[0], row[1]) for row in rows]) + u'.'

    def send_simple_reply(self, mess, text, private=False):
        """
        Splits long messages and sends them in parts.
        """
        linelimit = 30
        delay = 2

        lines = text.split(u'\n')
        parent = super(ardjbot, self)
        if len(lines) <= linelimit:
            return parent.send_simple_reply(mess, text, private)

        current = 1
        total = math.ceil(float(len(lines)) / float(linelimit))
        parent.send_simple_reply(mess, u'The response it too long (%u lines), sending in %u messages, up to %u lines each, with a %u seconds delay.' % (len(lines), total, linelimit, delay), private)
        while len(lines):
            prefix = u'[part %u of %u]\n<br/>' % (current, total)
            parent.send_simple_reply(mess, prefix + u'\n'.join(lines[:linelimit]), private)
            del lines[:linelimit]
            current += 1
            time.sleep(delay)

    def get_linked_sender(self, message):
        name, host = message.getFrom().getStripped().split('@')
        return u'<a href="xmpp:%s@%s">%s</a>' % (name, host, name)

    def send_signal(self, sig, prog):
        """
        Sends a signal to the specified program. Returns True on success.
        """
        cmd = '/usr/bin/killall'
        if not os.path.exists(cmd):
            raise Exception(u'%s is not available.' % cmd)
        if subprocess.Popen([cmd, '-' + sig, prog]).wait():
            raise Exception(u'Could not skip. Is '+ prog +' running?')
        return True

    def connect(self):
        """
        Extends the parent method by registering a disconnect handler.
        """
        conn = super(ardjbot, self).connect()
        # this is now done while calling serve_forever().
        # conn.RegisterDisconnectHandler(self.on_disconnect)
        return conn

    def on_disconnect(self):
        log('on_disconnect called.')
        if self.dbtracker:
            log('on_disconnect: stopping dbtracker.')
            self.dbtracker.stop()
            self.dbtracker = None
            log('on_disconnect: finished.')

    def __vote(self, track_id, email, vote):
        return (1, self.ardj.database.add_vote(track_id, email, vote))

        cur = self.ardj.database.cursor()
        # store the vote
        cur.execute('DELETE FROM votes WHERE track_id = ? AND email = ?', (track_id, email, ))
        cur.execute('INSERT INTO votes (track_id, email, vote) VALUES (?, ?, ?)', (track_id, email, vote, ))
        # update track weight
        votes = cur.execute('SELECT SUM(vote) FROM votes WHERE track_id = ?', (track_id, )).fetchall()[0][0]
        weight = max(1 + votes * 0.25, 0.1)
        cur.execute('UPDATE tracks SET weight = ? WHERE id = ?', (weight, track_id, ))
        return (votes, weight)

def Open(ardj):
    """
    Returns a new bot instance.
    """
    return ardjbot(ardj)

__all__ = ['Open']
