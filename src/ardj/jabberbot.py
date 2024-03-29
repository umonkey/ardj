#!/usr/bin/python
# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:

# JabberBot: A simple jabber/xmpp bot framework
# Copyright (c) 2007-2010 Thomas Perl <thpinfo.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import inspect
import logging
import os
import re
import sys
import time
import traceback

try:
    import xmpp
except ImportError:
    print('You need to install xmpppy from http://xmpppy.sf.net/.', file=sys.stderr)
    sys.exit(-1)

"""A simple jabber/xmpp bot framework"""

__author__ = 'Thomas Perl <thp@thpinfo.com>'
__version__ = '0.10'
__website__ = 'http://thpinfo.com/2007/python-jabberbot/'
__license__ = 'GPLv3 or later'


def botcmd(*args, **kwargs):
    """Decorator for bot command functions"""

    def decorate(func, hidden=False, name=None, pattern=None):
        setattr(func, '_jabberbot_command', True)
        setattr(func, '_jabberbot_hidden', hidden)
        setattr(func, '_jabberbot_command_name', name or func.__name__)
        setattr(func, '_jabberbot_command_re', pattern and re.compile(pattern))
        return func

    if len(args):
        return decorate(args[0], **kwargs)
    else:
        return lambda func: decorate(func, **kwargs)


class JabberBot(object):
    AVAILABLE, AWAY, CHAT, DND, XA, OFFLINE = None, 'away', 'chat', 'dnd', 'xa', 'unavailable'

    MSG_AUTHORIZE_ME = 'Hey there. You are not yet on my roster. Authorize my request and I will do the same.'
    MSG_NOT_AUTHORIZED = 'You did not authorize my subscription request. Access denied.'

    PROCESS_MSG_FROM_SELF = False
    PROCESS_MSG_FROM_UNSEEN = False

    def __init__(self, username, password, res=None, debug=False):
        """Initializes the jabber bot and sets up commands."""
        self.__debug = debug
        self.log = logging.getLogger(__name__)
        self.__username = username
        self.__password = password
        self.jid = xmpp.JID(self.__username)
        self.res = (res or self.__class__.__name__)
        self.conn = None
        self.__finished = False
        self.__exitcode = 0
        self.__show = None
        self.__status = None
        self.__seen = {}
        self.__threads = {}

        self.commands = {}
        for name, value in inspect.getmembers(self):
            if inspect.ismethod(value) and getattr(
                    value, '_jabberbot_command', False):
                name = getattr(value, '_jabberbot_command_name')
                if self.__debug:
                    self.log.debug('Registered command: %s' % name)
                self.commands[name] = value

        self.roster = None

################################

    def _send_status(self):
        self.conn.send(
            xmpp.dispatcher.Presence(
                show=self.__show,
                status=self.__status))

    def __set_status(self, value):
        if self.__status != value:
            self.__status = value
            self._send_status()

    def __get_status(self):
        return self.__status

    status_message = property(fget=__get_status, fset=__set_status)

    def __set_show(self, value):
        if self.__show != value:
            self.__show = value
            self._send_status()

    def __get_show(self):
        return self.__show

    status_type = property(fget=__get_show, fset=__set_show)

################################

    def connect(self):
        if not self.conn:
            if self.__debug:
                conn = xmpp.Client(self.jid.getDomain())
            else:
                conn = xmpp.Client(self.jid.getDomain(), debug=[])

            conres = conn.connect()
            if not conres:
                self.log.error(
                    'unable to connect to server %s.' %
                    self.jid.getDomain())
                return None
            if conres != 'tls':
                self.log.warning(
                    'unable to establish secure connection - TLS failed!')

            authres = conn.auth(self.jid.getNode(), self.__password, self.res)
            if not authres:
                self.log.error('unable to authorize with server.')
                return None
            if authres != 'sasl':
                self.log.warning(
                    "unable to perform SASL auth os %s. Old authentication method used!" %
                    self.jid.getDomain())

            conn.sendInitPresence()
            self.conn = conn
            self.roster = self.conn.Roster.getRoster()
            roster_items = sorted(self.roster.getItems())
            self.log.info('*** roster (%u) ***' % len(roster_items))
            for contact in roster_items:
                self.log.info('  %s' % contact)
            self.log.info('*** roster ***')
            self.conn.RegisterHandler('message', self.callback_message)
            self.conn.RegisterHandler('presence', self.callback_presence)

        return self.conn

    def join_room(self, room, username=None):
        """Join the specified multi-user chat room"""
        if username is None:
            username = self.__username.split('@')[0]
        my_room_JID = '/'.join((room, username))
        self.connect().send(xmpp.Presence(to=my_room_JID))

    def quit(self, exitcode=0):
        """Stop serving messages and exit.

        I find it is handy for development to run the
        jabberbot in a 'while true' loop in the shell, so
        whenever I make a code change to the bot, I send
        the 'reload' command, which I have mapped to call
        self.quit(), and my shell script relaunches the
        new version.
        """
        self.__finished = True
        self.__exitcode = exitcode

    def send_message(self, mess):
        """Send an XMPP message"""
        self.connect().send(mess)

    def send_tune(self, song, debug=False):
        """Set information about the currently played tune

        Song is a dictionary with keys: file, title, artist, album, pos, track,
        length, uri. For details see <http://xmpp.org/protocols/tune/>.
        """
        NS_TUNE = 'http://jabber.org/protocol/tune'
        iq = xmpp.Iq(typ='set')
        iq.setFrom(self.jid)
        iq.pubsub = iq.addChild('pubsub', namespace=xmpp.NS_PUBSUB)
        iq.pubsub.publish = iq.pubsub.addChild(
            'publish', attrs={'node': NS_TUNE})
        iq.pubsub.publish.item = iq.pubsub.publish.addChild(
            'item', attrs={'id': 'current'})
        tune = iq.pubsub.publish.item.addChild('tune')
        tune.setNamespace(NS_TUNE)

        title = None
        if 'title' in song:
            title = song['title']
        elif 'file' in song:
            title = os.path.splitext(os.path.basename(song['file']))[0]
        if title is not None:
            tune.addChild('title').addData(title)
        if 'artist' in song:
            tune.addChild('artist').addData(song['artist'])
        if 'album' in song:
            tune.addChild('source').addData(song['album'])
        if 'pos' in song and song['pos'] > 0:
            tune.addChild('track').addData(str(song['pos']))
        if 'time' in song:
            tune.addChild('length').addData(str(song['time']))
        if 'uri' in song:
            tune.addChild('uri').addData(song['uri'])

        if debug:
            print('Sending tune:', iq.__str__().encode('utf8'))
        self.conn.send(iq)

    def send(self, user, text, in_reply_to=None, message_type='chat'):
        """Sends a simple message to the specified user."""
        mess = self.build_message(text)
        mess.setTo(user)

        if in_reply_to:
            mess.setThread(in_reply_to.getThread())
            mess.setType(in_reply_to.getType())
        else:
            mess.setThread(self.__threads.get(user, None))
            mess.setType(message_type)

        self.send_message(mess)

    def send_simple_reply(self, mess, text, private=False):
        """Send a simple response to a message"""
        self.send_message(self.build_reply(mess, text, private))

    def build_reply(self, mess, text=None, private=False):
        """Build a message for responding to another message.  Message is NOT sent"""
        response = self.build_message(text)
        if private:
            response.setTo(mess.getFrom())
            response.setType('chat')
        else:
            response.setTo(mess.getFrom())  # was: .getStripped() -- why?!
            response.setType(mess.getType())
        response.setThread(mess.getThread())
        return response

    def build_message(self, text):
        """Builds an xhtml message without attributes."""
        text_plain = re.sub(r'<[^>]+>', '', text)
        message = xmpp.protocol.Message(body=text_plain)
        if text_plain != text:
            html = xmpp.Node(
                'html', {
                    'xmlns': 'http://jabber.org/protocol/xhtml-im'})
            try:
                html.addChild(
                    node=xmpp.simplexml.XML2Node(
                        "<body xmlns='http://www.w3.org/1999/xhtml'>" +
                        text.encode('utf-8') +
                        "</body>"))
                message.addChild(node=html)
            except Exception as e:
                # Didn't work, incorrect markup or something.
                # print >> sys.stderr, e, text
                message = xmpp.protocol.Message(body=text_plain)
        return message

    def get_sender_username(self, mess):
        """Extract the sender's user name from a message"""
        type = mess.getType()
        jid = mess.getFrom()
        if type == "groupchat":
            username = jid.getResource()
        elif type == "chat":
            username = jid.getNode()
        else:
            username = ""
        return username

    def status_type_changed(self, jid, new_status_type):
        """Callback for tracking status types (available, away, offline, ...)"""
        if self.__debug:
            self.log.debug(
                'user %s changed status to %s' %
                (jid, new_status_type))

    def status_message_changed(self, jid, new_status_message):
        """Callback for tracking status messages (the free-form status text)"""
        if self.__debug:
            self.log.debug(
                'user %s updated text to %s' %
                (jid, new_status_message))

    def broadcast(self, message, only_available=False):
        """Broadcast a message to all users 'seen' by this bot.

        If the parameter 'only_available' is True, the broadcast
        will not go to users whose status is not 'Available'."""
        for jid, (show, status) in list(self.__seen.items()):
            if not only_available or show is self.AVAILABLE:
                self.send(jid, message)

    def callback_presence(self, conn, presence):
        jid, type_, show, status = presence.getFrom(), \
            presence.getType(), presence.getShow(), \
            presence.getStatus()

        if self.jid.bareMatch(jid):
            # Ignore our own presence messages
            return

        if type_ is None:
            # Keep track of status message and type changes
            old_show, old_status = self.__seen.get(jid, (self.OFFLINE, None))
            if old_show != show:
                self.status_type_changed(jid, show)

            if old_status != status:
                self.status_message_changed(jid, status)

            self.__seen[jid] = (show, status)
        elif type_ == self.OFFLINE and jid in self.__seen:
            # Notify of user offline status change
            del self.__seen[jid]
            self.status_type_changed(jid, self.OFFLINE)

        try:
            subscription = self.roster.getSubscription(str(jid))
        except KeyError as e:
            # User not on our roster
            subscription = None
        except AttributeError as e:
            # Recieved presence update before roster built
            return

        if type_ == 'error':
            self.log.error('Presence error: %s' % presence.getError())

        if self.__debug:
            self.log.debug(
                'Got presence: %s (type: %s, show: %s, status: %s, subscription: %s)' %
                (jid, type_, show, status, subscription))

        if type_ == 'subscribe':
            # Incoming presence subscription request
            if subscription in ('to', 'both', 'from'):
                self.roster.Authorize(jid)
                self._send_status()

            if subscription not in ('to', 'both'):
                self.roster.Subscribe(jid)

            if subscription in (None, 'none'):
                self.send(jid, self.MSG_AUTHORIZE_ME)
        elif type_ == 'subscribed':
            # Authorize any pending requests for that JID
            self.roster.Authorize(jid)
        elif type_ == 'unsubscribed':
            # Authorization was not granted
            self.send(jid, self.MSG_NOT_AUTHORIZED)
            self.roster.Unauthorize(jid)

    def callback_message(self, conn, mess):
        """Messages sent to the bot will arrive here. Command handling + routing is done in this function."""

        # Prepare to handle either private chats or group chats
        type = mess.getType()
        jid = mess.getFrom()
        props = mess.getProperties()
        text = mess.getBody()
        username = self.get_sender_username(mess)

        if type not in ("groupchat", "chat"):
            self.log.debug("unhandled message type: %s" % type)
            return

        self.log.debug("*** props = %s" % props)
        self.log.debug("*** jid = %s" % jid)
        self.log.debug("*** username = %s" % username)
        self.log.debug("*** type = %s" % type)
        self.log.debug("*** text = %s" % text)

        # Ignore messages from before we joined
        if xmpp.NS_DELAY in props:
            return

        # Ignore messages from myself
        if not self.PROCESS_MSG_FROM_SELF and username == self.__username:
            return

        # If a message format is not supported (eg. encrypted), txt will be
        # None
        if not text:
            return

        # Ignore messages from users not seen by this bot
        if not self.PROCESS_MSG_FROM_UNSEEN and jid not in self.__seen:
            self.log.info('Ignoring message from unseen guest: %s' % jid)
            self.log.debug(
                "I've seen: %s" % [
                    "%s" % x for x in list(
                        self.__seen.keys())])
            return

        # Remember the last-talked-in thread for replies
        self.__threads[jid] = mess.getThread()

        handler, command, args = self.parse_command(text)
        self.log.debug("*** cmd = %s" % command)

        try:
            if handler is not None:
                reply = handler(mess, args)
            else:
                # In private chat, it's okay for the bot to always respond.
                # In group chat, the bot should silently ignore commands it
                # doesn't understand or aren't handled by unknown_command().
                default_reply = 'Unknown command: "%s". Type "help" for available commands.' % command
                if type == "groupchat":
                    default_reply = None
                reply = self.unknown_command(mess, command, args)
                if reply is None:
                    reply = default_reply
        except Exception as e:
            reply = traceback.format_exc(e)
            self.log.exception(
                'An error happened while processing a message ("%s") from %s: %s"' %
                (text, jid, reply))
        if reply:
            self.send_simple_reply(mess, reply)

    def parse_command(self, text):
        # First look for commands with regular expressions.
        for command in self.commands:
            pattern = getattr(self.commands[command], '_jabberbot_command_re')
            if pattern is not None:
                res = pattern.match(text)
                if res is not None:
                    return self.commands[command], command, res.groups()
        # Find regular commands.
        if ' ' in text:
            command, args = text.split(' ', 1)
        else:
            command, args = text, ''
        command = command.lower()
        # Get the handler function.
        handler = command in self.commands and self.commands[command] or None
        # If the command has a regexp -- skip it, beacuse it didn't match.
        # Also, handlers of such commands expect args to be tuples, and we only
        # have a string.
        if hasattr(handler, '_jabberbot_command_re') and getattr(
                handler, '_jabberbot_command_re'):
            handler = None
        return handler, command, args

    def unknown_command(self, mess, cmd, args):
        """Default handler for unknown commands

        Override this method in derived class if you
        want to trap some unrecognized commands.  If
        'cmd' is handled, you must return some non-false
        value, else some helpful text will be sent back
        to the sender.
        """
        return None

    def top_of_help_message(self):
        """Returns a string that forms the top of the help message

        Override this method in derived class if you
        want to add additional help text at the
        beginning of the help message.
        """
        return ""

    def bottom_of_help_message(self):
        """Returns a string that forms the bottom of the help message

        Override this method in derived class if you
        want to add additional help text at the end
        of the help message.
        """
        return ""

    @botcmd
    def help(self, mess, args):
        """Returns a help string listing available options.

        Automatically assigned to the "help" command."""
        if not args:
            if self.__doc__:
                description = self.__doc__.strip()
            else:
                description = 'Available commands:'

            usage = '\n'.join(sorted([
                '%s: %s' % (
                    name,
                    (command.__doc__.strip() or '(undocumented)').split(
                        '\n',
                        1)[0])
                for (name, command) in self.commands.items() if name != 'help' and not command._jabberbot_hidden
            ]))
            usage = usage + '\n\nType help <command name> to get more info about that specific command.'
        else:
            description = ''
            if args in self.commands:
                usage = self.commands[args].__doc__.strip() or 'undocumented'
            else:
                usage = 'That command is not defined.'

        top = self.top_of_help_message()
        bottom = self.bottom_of_help_message()
        if top:
            top = "%s\n\n" % top
        if bottom:
            bottom = "\n\n%s" % bottom

        return '%s%s\n\n%s%s' % (top, description, usage, bottom)

    def idle_proc(self):
        """This function will be called in the main loop."""
        pass

    def shutdown(self):
        """This function will be called when we're done serving

        Override this method in derived class if you
        want to do anything special at shutdown.
        """
        pass

    def serve_forever(self, connect_callback=None, disconnect_callback=None):
        """Connects to the server and handles messages."""
        conn = self.connect()
        if conn:
            self.log.info('bot connected. serving forever.')
        else:
            self.log.warn('could not connect to server - aborting.')
            return self.__exitcode

        if connect_callback:
            connect_callback()

        while not self.__finished:
            try:
                conn.Process(10)
                self.idle_proc()
            except KeyboardInterrupt:
                self.log.info('bot stopped by user request. shutting down.')
                break

        self.shutdown()

        if disconnect_callback:
            disconnect_callback()

        return self.__exitcode
