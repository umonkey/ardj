# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:

import logging
import os
import signal
import socket  # for gethostname()
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
import ardj.settings
import ardj.tracks
import ardj.util


class MyFileReceivingBot(FileBot):
    def is_file_acceptable(self, sender, filename, filesize):
        if not self.check_access(sender):
            logging.warning('Refusing to accept files from %s.' % sender)
            raise FileNotAcceptable('I\'m not allowed to receive files from you, sorry.')
        if os.path.splitext(filename.lower())[1] not in ['.mp3', '.ogg', '.zip']:
            raise FileNotAcceptable('I only accept MP3, OGG and ZIP files, which "%s" doesn\'t look like.' % os.path.basename(filename))

    def callback_file(self, sender, filename):
        tmpname = None
        sender = sender.split('/')[0]  # remove the resource
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
        logging.info('Received %s.' % filename)
        track_id = ardj.tracks.add_file(filename, labels=['incoming', 'incoming-jabber'], queue=True)
        time.sleep(1)  # let ezstream read some data
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
        self.lastping = None  # время последнего пинга
        self.pidfile = '/tmp/ardj-jabber.pid'
        self.database_mtime = None

        self.chat_users = []

        _conf = ardj.settings.get2("jabber_id", "jabber/login")
        self.login, password = self.split_login(_conf)
        resource = socket.gethostname() + '/' + str(os.getpid()) + '/'
        super(ardjbot, self).__init__(self.login, password, res=resource, debug=debug)

    def split_login(self, uri):
        name, password = uri.split('@', 1)[0].split(':', 1)
        host = uri.split('@', 1)[1]
        return (name + '@' + host, password)

    def idle_proc(self):
        """
        Updates the status, pings the server.
        """
        try:
            self.__idle_status()
            self.__idle_ping()
            self.send_pending_messages()
            ardj.tracks.do_idle_tasks(self.set_busy)
        except Exception, e:
            ardj.log.log_error("ERROR in jabber idle handlers: %s" % e, e)

        try:
            ardj.database.commit()
        except Exception, e:
            logging.error("Could not commit changes: %s." % e)

        super(ardjbot, self).idle_proc()

    def set_busy(self):
        self.status = self.DND

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
            #logging.debug('Pinging the server.')
            ping = xmpp.Protocol('iq', typ='get', payload=[xmpp.Node('ping', attrs={'xmlns':'urn:xmpp:ping'})])
            try:
                res = self.conn.SendAndWaitForResponse(ping, self.PING_TIMEOUT)
                #logging.debug('Got response: ' + str(res))
                if res is None:
                    logging.error('Terminating due to PING timeout.')
                    self.quit(1)
            except IOError, e:
                logging.error('Error pinging the server: %s, shutting down.' % e)
                self.quit(1)

    def on_connected(self):
        logging.debug('on_connected called.')
        self.lastping = time.time()
        if self.pidfile:
            try:
                open(self.pidfile, 'w').write(str(os.getpid()))
            except IOError, e:
                logging.error(u'Could not write to %s: %s' % (self.pidfile, e))
        self.update_status()
        self.join_chat_room()

    def join_chat_room(self):
        """Joins the chat room if configured."""
        jid = self.get_chat_room_jid()
        if not jid:
            return
        parts = jid.split('/', 1)
        if len(parts) == 1:
            parts.append(None)
        logging.debug("Trying to join chat room %s" % jid)
        self.join_room(parts[0], parts[1])

    def say_to_chat(self, message):
        """Sends a message to the chat room, if it's configured."""
        jid = self.get_chat_room_jid()
        if jid:
            self.say_to_jid(jid, message, group=True)

    def get_chat_room_jid(self):
        """Returns the JID of the chat room.  The reason for not reading this
        once and storing in the instance is that the configuration file can
        change any time."""
        return ardj.settings.get("jabber_chat_room", ardj.settings.get("jabber/chat_room"))

    def say_to_jid(self, jid, message, group=False):
        msg = self.build_message(message)
        msg.setTo(jid.split('/')[0])
        if group:
            msg.setType('groupchat')
        else:
            msg.setType('chat')
        self.send_message(msg)

    def shutdown(self):
        # self.on_disconnect() # called by JabberBot afterwards.
        logging.info('shutdown: shutting down JabberBot.')
        JabberBot.shutdown(self)
        if self.pidfile and os.path.exists(self.pidfile):
            logging.debug('shutdown: removing the pid file.')
            os.unlink(self.pidfile)
        logging.info('shutdown: over.')

    def update_status(self, onstart=False):
        """
        Updates the status with the current track name.
        """
        try:
            if ardj.settings.get2("use_jabber_status", "jabber/status", False):
                message = ardj.console.process_command('status')
                if message != self.status_message:
                    self.status_message = message
        except Exception, e:
            self.status_message = 'Error updating status: %s' % e
        """ FIXME
        if ardj.settings.get2('use_jabber_tunes', 'jabber/tunes', True):
            self.send_tune(track)
        """

    def callback_presence(self, conn, presence):
        """Tracks chat room users."""
        jid = unicode(presence.getFrom())
        chat_jid = (self.get_chat_room_jid() or "").split("/")[0]
        if chat_jid == jid.split("/")[0]:
            type_ = presence.getType()
            if type_ == "unavailable" and jid in self.chat_users:
                self.chat_users.remove(jid)
                logging.debug("%s left the chat room." % jid.encode("utf-8"))
                self._update_chat_room_stats()
            elif type_ is None and jid not in self.chat_users:
                self.chat_users.append(jid)
                logging.debug("%s joined the chat room." % jid.encode("utf-8"))
                self._update_chat_room_stats()
        return super(ardjbot, self).callback_presence(conn, presence)

    def _update_chat_room_stats(self):
        """Saves the number of users to a file.

        The file name can be specified with the jabber_chat_counter config option."""
        count = len(self.chat_users)
        logging.debug("Chat room has %u users." % count)

        fn = ardj.settings.getpath("jabber_chat_counter")
        if fn:
            file(fn, "wb").write(str(count))

    def callback_message(self, conn, mess):
        """Extended message handler.

        Adds an explicit database commit after all messages.
        """
        if self._handle_chat_room_message(mess):
            return

        if mess.getType() == 'chat':
            try:
                msg = mess.getBody()
                if not msg:
                    return
                rep = ardj.console.process_command(msg, mess.getFrom().getStripped())
            except Exception, e:
                ardj.log.log_error("ERROR: %s, MESSAGE: %s" % (e, mess.getBody().encode("utf-8")), e)
                rep = unicode(e)
            ardj.database.commit()
            if isinstance(rep, (str, unicode)):
                self.send_simple_reply(mess, rep.strip())
            self.send_pending_messages()
            self.status_type = self.AVAILABLE

    def _handle_chat_room_message(self, mess):
        """Handles private chat room messages by telling the user to send
        messages directly to the bot jid."""
        if mess.getType() != "chat":
            return False

        chat_room_jid = self.get_chat_room_jid()
        if chat_room_jid is None:
            return False

        sender = mess.getFrom().getStripped()
        if sender == chat_room_jid.split("/")[0]:
            self.send_simple_reply(mess, u"You are sending me a private "
                "message through a chat room.  I don't work this way.  Please "
                "add me to your roster as %s and let's talk there." % self.login)
            return True

        return False

    def send_pending_messages(self):
        """Sends all pending messages to the chat room or exact recipients.
        Messages are added to the queue using the chat_say() function."""
        try:
            commit = False
            for msg in ardj.database.Message.find_all():
                if msg.get("re"):
                    self.say_to_jid(msg["re"], msg["message"])
                else:
                    self.say_to_chat(msg["message"])
                msg.delete()
                commit = True
            if commit:
                ardj.database.commit()
        except Exception, e:
            ardj.log.log_error("Could not send pending messages: %s" % e, e)

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
        logging.debug('on_disconnect called.')


class TestBot(JabberBot):
    """A client for connection testing"""
    PING_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        self.lastping = time.time()
        JabberBot.__init__(self, *args, **kwargs)

    @botcmd
    def die(self, mess, args):
        self.quit()
        return 'Ok, bye.'

    @botcmd
    def check(self, mess, args):
        pass

    def idle_proc(self):
        if time.time() - self.lastping > 5:
            self.lastping = time.time()
            ping = xmpp.Protocol('iq', typ='get',
                payload=[xmpp.Node('ping', attrs={'xmlns':'urn:xmpp:ping'})])
            res = self.conn.SendAndWaitForResponse(ping, 1)
            print 'GOT:', res


def Open(debug=False):
    """Returns a new bot instance."""
    if ardj.settings.get2("jabber_id", "jabber/login") is not None:
        return ardjbot(debug=debug)


def chat_say(message, recipient=None):
    """Adds a message to the chat room queue.  This is the only way for command
    handlers to notify chat users.  If the recipient is not specified, the
    message is sent to the chat room."""
    ardj.database.execute("INSERT INTO jabber_messages (re, message) VALUES (?, ?)", (recipient, message, ))
    ardj.database.commit()


def cmd_run_bot(*args, **kwargs):
    """Run the jabber bot"""
    debug = "--debug" in args
    bot = Open(debug=debug)
    if bot is not None:
        bot.run()


def cmd_probe(jid=None, password=None, *args, **kwargs):
    """Perform a test connection, args: jid, password."""
    from cli import UsageError

    if jid is None:
        raise UsageError("Specify a JID.")

    if password is None:
        raise UsageError("Specify a password.")

    bot = TestBot(jid, password, res="debug/", debug=True)
    bot.serve_forever()


__all__ = ['Open', 'chat_say']
