# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:

import os
import signal
import socket # for gethostname()
import time
import traceback
import zipfile
from xml.sax import saxutils

from ardj.jabberbot import JabberBot, botcmd
from ardj.filebot import FileBot, FileNotAcceptable
from ardj import xmpp

import ardj.console
import ardj.database
import ardj.log
import ardj.scrobbler
import ardj.settings
import ardj.tracks
import ardj.util

USAGE = """Usage: ardj jabber command

Commands:
  restart       -- restart the bot and ices
  run           -- run the bot (safety wrapper)
  run-child     -- run the jabber bot itself (unsafe)
"""

class MyFileReceivingBot(FileBot):
    def is_file_acceptable(self, sender, filename, filesize):
        if not self.check_access(sender):
            ardj.log.warning('Refusing to accept files from %s.' % sender)
            raise FileNotAcceptable('I\'m not allowed to receive files from you, sorry.')
        if os.path.splitext(filename.lower())[1] not in ['.mp3', '.ogg', '.zip']:
            raise FileNotAcceptable('I only accept MP3, OGG and ZIP files, which "%s" doesn\'t look like.' % os.path.basename(filename))

    def callback_file(self, sender, filename):
        tmpname = None
        sender = sender.split('/')[0] # remove the resource
        try:
            ids = []
            if filename.lower().endswith('.zip'):
                try:
                    zip = zipfile.ZipFile(filename)
                    for zipname in zip.namelist():
                        ext = os.path.splitext(zipname.lower())[1]
                        if ext in ('.mp3', '.ogg'):
                            tmpname = 'tmp' + ext
                            tmp = open(tmpname, 'wb')
                            tmp.write(zip.read(zipname))
                            tmp.close()
                            ids.append(str(self.process_incoming_file(sender, tmpname)))
                            os.unlink(tmpname)
                except zipfile.BadZipfile, e:
                    return u'Your ZIP file is damaged.'
            else:
                ids.append(str(self.process_incoming_file(sender, filename)))
            return u'Your files were scheduled for playing, their ids are: %s. Use the \'news\' command to see more details about the files. Use the \'batch tags ...\' command to add tags to uploaded files (will only work once).' % u', '.join(ids)
        finally:
            if tmpname is not None and os.path.exists(tmpname):
                os.unlink(tmpname)
            ardj.database.Open().commit()

    def process_incoming_file(self, sender, filename):
        ardj.log.info('Received %s.' % filename)
        track_id = ardj.tracks.add_file(filename, labels=['incoming', 'incoming-jabber'], queue=True)
        time.sleep(1) # let ices read some data
        return track_id

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

    def __init__(self, debug=False):
        self.lastping = None # время последнего пинга
        self.pidfile = '/tmp/ardj-jabber.pid'
        self.database_mtime = None

        self.lastfm = ardj.scrobbler.LastFM()
        self.librefm = ardj.scrobbler.LibreFM()

        login, password = self.split_login(ardj.settings.get('jabber/login', fail=True))
        resource = socket.gethostname() + '/' + str(os.getpid()) + '/'
        super(ardjbot, self).__init__(login, password, res=resource, debug=debug)

    def split_login(self, uri):
        name, password = uri.split('@', 1)[0].split(':', 1)
        host = uri.split('@', 1)[1]
        return (name + '@' + host, password)

    def idle_proc(self):
        """
        Updates the status, pings the server.
        """
        self.__idle_status()
        self.__idle_ping()
        self.__idle_lastfm()
        self.__idle_incoming()
        self.send_pending_messages()
        super(ardjbot, self).idle_proc()

    def __idle_incoming(self):
        """Sees if there's new music and processes it."""
        try:
            files = ardj.tracks.find_incoming_files()
            if files:
                self.status_type = self.DND
                success = []
                add_labels = ardj.settings.get('database/incoming/labels', [ 'tagme', 'music' ])
                for filename in files:
                    folder = os.path.dirname(filename)
                    if not os.access(folder, os.W_OK):
                        ardj.log.warning('File %s can not be deleted -- not adding.' % filename)
                    else:
                        ardj.tracks.add_file(filename, add_labels)
                        os.unlink(filename)
                        time.sleep(1)
                        success.append(os.path.basename(filename))
                self.status_type = self.AVAILABLE
                if success:
                    chat_say('%u new files added, see the "news" command.' % len(success))
        except Exception, e:
            ardj.log.error('Error adding new files: %s' % e)

    def __idle_lastfm(self):
        cur = ardj.database.cursor()
        commit = False
        if self.lastfm:
            try:
                if self.lastfm.process(cur=cur):
                    commit = True
            except Exception, e:
                ardj.log.error('Could not process LastFM queue: %s' % e)

        if self.librefm:
            try:
                if self.librefm.process(cur=cur):
                    commit = True
            except Exception, e:
                ardj.log.error('Could not process LibreFM queue: %s' % e)

        if commit:
            ardj.database.commit()

    def __idle_status(self):
        """
        Changes status when the database changes.
        """
        db = ardj.database.Open()
        stat = os.stat(db.filename)
        if self.database_mtime is None or self.database_mtime < stat.st_mtime:
            self.database_mtime = stat.st_mtime
            self.update_status()

    def __idle_ping(self):
        """
        Pings the server, shuts the bot down if no response is received.
        """
        if time.time() - self.lastping > self.PING_FREQUENCY:
            self.lastping = time.time()
            #ardj.log.debug('Pinging the server.')
            ping = xmpp.Protocol('iq',typ='get',payload=[xmpp.Node('ping',attrs={'xmlns':'urn:xmpp:ping'})])
            try:
                res = self.conn.SendAndWaitForResponse(ping, self.PING_TIMEOUT)
                #ardj.log.debug('Got response: ' + str(res))
                if res is None:
                    ardj.log.error('Terminating due to PING timeout.')
                    self.quit(1)
            except IOError, e:
                ardj.log.error('Error pinging the server: %s, shutting down.' % e)
                self.quit(1)

    def on_connected(self):
        ardj.log.debug('on_connected called.')
        self.lastping = time.time()
        if self.pidfile:
            try:
                open(self.pidfile, 'w').write(str(os.getpid()))
            except IOError, e:
                ardj.log.error(u'Could not write to %s: %s' % (self.pidfile, e))
        self.update_status()
        self.join_chat_room()

        if not self.lastfm.authorize():
            self.lastfm = None
        if not self.librefm.authorize():
            self.librefm = None

    def join_chat_room(self):
        """Joins the chat room if configured."""
        jid = ardj.settings.get('jabber/chat_room')
        parts = jid.split('/', 1)
        if len(parts) == 1:
            parts.append(None)
        self.join_room(parts[0], parts[1])

    def say_to_chat(self, message):
        """Sends a message to the chat room, if it's configured."""
        jid = ardj.settings.get('jabber/chat_room')
        if jid:
            ardj.log.debug(u'Trying to send to "%s" to %s' % (message, jid))
            msg = self.build_message(message)
            ardj.log.debug(msg)
            msg.setTo(jid.split('/')[0])
            msg.setType('groupchat')
            self.send_message(msg)

    def shutdown(self):
        # self.on_disconnect() # called by JabberBot afterwards.
        ardj.log.info('shutdown: shutting down JabberBot.')
        JabberBot.shutdown(self)
        if self.pidfile and os.path.exists(self.pidfile):
            ardj.log.debug('shutdown: removing the pid file.')
            os.unlink(self.pidfile)
        ardj.log.info('shutdown: over.')

    def update_status(self, onstart=False):
        """
        Updates the status with the current track name.
        """
        try:
            if ardj.settings.get('jabber/status', False):
                message = ardj.console.process_command('status')
                if message != self.status_message:
                    self.status_message = message
        except Exception, e:
            self.status_message = 'Error updating status: %s' % e
        """ FIXME
        if ardj.settings.get('jabber/tunes', True):
            self.send_tune(track)
        """

    def callback_message(self, conn, mess):
        """Extended message handler.

        Adds an explicit database commit after all messages.
        """
        try:
            if mess.getType() == 'chat':
                try:
                    msg = mess.getBody()
                    if not msg:
                        return
                    rep = ardj.console.process_command(msg, mess.getFrom().getStripped())
                except Exception, e:
                    ardj.log.warning(u'ERROR: %s, MESSAGE: %s\n%s' % (e, mess, traceback.format_exc(e)))
                    rep = unicode(e)
                self.send_simple_reply(mess, rep.strip())
                self.send_pending_messages()
        finally:
            ardj.database.commit()

    def send_pending_messages(self):
        """Sends outgoing messages added using the chat_say() function."""
        cur = ardj.database.cursor()
        messages = cur.execute('SELECT id, re, message FROM jabber_messages')
        for msgid, recipient, message in messages:
            if recipient is None:
                self.say_to_chat(message)
            else:
                pass
            cur.execute('DELETE FROM jabber_messages WHERE id = ?', (msgid, ))

    def run(self):
        return self.serve_forever(connect_callback=self.on_connected, disconnect_callback=self.on_disconnect)

    def connect(self):
        """
        Extends the parent method by registering a disconnect handler.
        """
        conn = super(ardjbot, self).connect()
        # this is now done while calling serve_forever().
        # conn.RegisterDisconnectHandler(self.on_disconnect)
        return conn

    def on_disconnect(self):
        ardj.log.debug('on_disconnect called.')

def Open(debug=False):
    """
    Returns a new bot instance.
    """
    return ardjbot(debug=debug)


def run_cli(args):
    """Implements the "ardj jabber" command."""
    if len(args) and args[0] == 'restart':
        for param in ('jabber/pid', 'jabber/ices_pid'):
            pidfile = ardj.settings.getpath(param, fail=True)
            if pidfile and os.path.exists(pidfile):
                pid = int(open(pidfile).read().strip())
                try: os.kill(pid, signal.SIGTERM)
                except OSError: pass
        return True

    if len(args) and args[0] == 'run-child':
        return Open(debug='--debug' in args).run()

    if len(args) and args[0] == 'run':
        delay = 5
        command = [ 'ardj', 'jabber', 'run-child' ]
        if '--debug' in args:
            command.append('--debug')
        while True:
            try:
                if ardj.util.run(command):
                    return True
                ardj.log.error('Unclean jabber bot shutdown, restarting in %u seconds.' % delay)
            except KeyboardInterrupt:
                ardj.log.info('Jabber bot killed by ^C.')
            time.sleep(delay)

    print USAGE


def chat_say(message, recipient=None):
    """Adds a message to the chat room queue.  This is the way for command
    handlers to notify chat users.  If the recipient is not specified, the
    message is sent to the chat room."""
    ardj.log.debug(u'Will send to chat: %s' % message)
    ardj.database.cursor().execute('INSERT INTO jabber_messages (re, message) VALUES (?, ?)', (recipient, message, ))


__all__ = [ 'Open', 'chat_say' ]
