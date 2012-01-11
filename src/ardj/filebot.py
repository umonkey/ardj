# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:
#
# RTFM:
#
# - SOCKS5 Bytestreams:
#   http://xmpp.org/extensions/xep-0065.html
# - SI File Transfer:
#   http://xmpp.org/extensions/xep-0096.html

import hashlib
import logging
import os
import socket
import socks
import tempfile
import time
import traceback
import xmpp
import xmpp.protocol

from ardj.jabberbot import JabberBot


class FileNotAcceptable(Exception):
    pass


class DiscoBot(JabberBot):
    def connect(self):
        """Add support for XEP-0115."""
        init = not self.conn
        conn = super(DiscoBot, self).connect()
        if conn and init:
            conn.RegisterHandler('iq', self.on_disco_info, ns=xmpp.NS_DISCO_INFO)
        return conn

    def on_disco_info(self, conn, mess):
        reply = mess.buildReply('result')
        query = reply.getTag('query')
        query.addChild('feature', {'var': xmpp.NS_SI})
        query.addChild('feature', {'var': xmpp.NS_BYTESTREAM})
        query.addChild('feature', {'var': xmpp.NS_FILE})
        conn.send(reply)
        raise xmpp.NodeProcessed


class FileBot(DiscoBot):
    SOCKET_TIMEOUT = 30  # seconds

    def __init__(self, username, password, res=None, debug=False):
        super(FileBot, self).__init__(username, password, res, debug)
        self.id = int(time.time())
        self.transfers = {}

    def is_file_acceptable(self, sender, filename, filesize):
        """
        Checks whether you want to receive a file.  By default all files
        are accepted; override to redefine this logic.
        """
        return True

    def callback_file(self, sender, filename):
        """
        Called when a file is successfully received.  The file should be moved
        to a new location.  If that is not done, the file is deleted when this
        method returns.

        If anything is returned, it's sent back to file sender as a message,
        e.g.: "Thank you for this file."
        """
        logging.info((u'Received file %s from %s.' % (filename, sender)).encode("utf-8"))

    #### You don't want to mess with the following code. ####

    def connect(self):
        """
        Add support for SI and Bytestream.
        """
        init = not self.conn
        conn = super(FileBot, self).connect()
        if conn and init:
            conn.RegisterHandler('iq', self.si_req_handler, ns=xmpp.NS_SI)
            conn.RegisterHandler('iq', self.on_bytestream, ns=xmpp.NS_BYTESTREAM)
        return conn

    def si_req_handler(self, conn, mess):
        """
        SI profile negotiation.
        """
        try:
            si = mess.getTag('si')
            logging.debug('Got Stream Initiation request #' + str(si.attrs['id']))
            for field in si.getTag('feature').getTag('x').getTags('field'):
                if field.attrs['var'] != 'stream-method':
                    logging.debug('Ignoring unsupported field type: ' + field.attrs['var'])
                else:
                    for option in field.getTags('option'):
                        if option.getTagData('value') != xmpp.NS_BYTESTREAM:
                            logging.debug('Ignoring unsupported stream type: ' + option.getTagData('value'))
                        else:
                            transfer = {
                                'from': unicode(mess.getFrom()),
                                'to': unicode(mess.getTo()),
                                'name': si.getTagAttr('file', 'name'),
                                'size': int(si.getTagAttr('file', 'size')),
                            }
                            try:
                                self.is_file_acceptable(transfer['from'], transfer['name'], transfer['size'])
                                self.transfers[si.attrs['id']] = transfer
                                reply = mess.buildReply('result')
                                reply.addChild('si', namespace=xmpp.NS_SI) \
                                    .addChild('feature', namespace=xmpp.NS_FEATURE) \
                                    .addChild('x', {'type': 'submit'}, namespace=xmpp.NS_DATA) \
                                    .addChild('field', {'var': 'stream-method'}) \
                                    .addChild('value', payload=[xmpp.NS_BYTESTREAM])
                                logging.debug('File transfer table:\n' + str(self.transfers))
                                conn.send(reply)
                                raise xmpp.NodeProcessed
                            except FileNotAcceptable, e:
                                reply = mess.buildReply('error')
                                reply.addChild('error', {'type': 'cancel'})
                                reply.addChild('forbidden')
                                reply.addChild('text', payload=unicode(e), namespace=xmpp.NS_STANZAS)
                                """Desired response:
                                <iq to="to" type="error" id="id">
                                <error code="403" type="cancel">
                                <forbidden />
                                <text xmlns="urn:ietf:params:xml:ns:xmpp-stanzas">Error Message</text>
                                </error>
                                </iq>
                                """
            logging.debug('Could not negotiate Stream Initiation for some reason.')
        except xmpp.NodeProcessed, e:
            raise e
        except Exception, e:
            logging.error('Error negotiating file transfer: %s' % e)
            logging.error(traceback.format_exc(e))

    def on_bytestream(self, conn, mess):
        """
        Tries to connect to all specified streamhosts.
        """
        logging.debug('Incoming streamhosts.')
        try:
            sid = unicode(mess.getTagAttr('query', 'sid'))
            if sid not in self.transfers:
                logging.debug('Ignoring streamhosts for unknown transfer: ' + sid)
            else:
                transfer = self.transfers[sid]
                logging.debug('Got streamhosts for transfer #%s: %s' % (sid, transfer))

                target_host = hashlib.sha1(sid + transfer['from'] + transfer['to']).hexdigest()
                target_port = 0

                for host in mess.getTag('query').getTags('streamhost'):
                    proxy_host = host.getAttr('host')
                    proxy_port = int(host.getAttr('port'))

                    logging.debug('Connecting to %s:%u via %s:%u' % (target_host, target_port, proxy_host, proxy_port))

                    try:
                        s = socks.socksocket()
                        s.setproxy(socks.PROXY_TYPE_SOCKS5, proxy_host, proxy_port)
                        s.connect((target_host, target_port))
                        s.setblocking(0)
                    except Exception, e:
                        logging.warning('Could not connect to %s:%u: %s' % (proxy_host, proxy_port, e))
                        continue

                    logging.debug('Socket %s connected to %s:%s, retrieving %u bytes.' % (s, proxy_host, proxy_port, transfer['size']))

                    # Store the file in a temporary folder to maintain its basename.
                    filename = os.path.join(tempfile.mkdtemp(prefix='jabberbot-'), os.path.basename(transfer['name']))

                    self.transfers[sid].update({
                        'socket': s,
                        'name': filename,
                        'file': open(filename, 'wb'),
                        'lastseen': int(time.time()),
                        'received': 0,
                    })

                    # Tell the sender that we're ready to go.
                    reply = mess.buildReply('result')
                    reply.getTag('query').addChild('streamhost-used', {'jid': host.getAttr('jid')})
                    conn.send(reply)

                    raise xmpp.NodeProcessed

            # If the Target is unwilling to accept the bytestream,
            # it MUST return a <not-acceptable/> error to the Requester.
            # http://xmpp.org/extensions/xep-0065.html

        except xmpp.NodeProcessed, e:
            raise e
        except Exception, e:
            logging.error('Error starting transfer: %s: %s' % (e.__class__.__name__, e))
            logging.error(traceback.format_exc(e))

    def idle_proc(self):
        """
        Checks for data in active sockets.  If all data is received for a file,
        calls callback_file().  If no data was received from a socket for
        as long as self.SOCKET_TIMEOUT seconds, the connection is dropped and
        the temporary file is deleted.
        """
        super(FileBot, self).idle_proc()
        for sid in self.transfers.keys():
            if 'socket' in self.transfers[sid]:
                transfer = self.transfers[sid]
                got = 0
                while True:
                    try:
                        data = transfer['socket'].recv(8192, socket.MSG_DONTWAIT)
                    except IOError, e:
                        break  # no data
                    if not data:
                        break
                    got += len(data)
                    transfer['file'].write(data)
                transfer['received'] += got
                if got:
                    transfer['lastseen'] = int(time.time())
                    self.transfers[sid] = transfer
                    logging.debug('Got %u bytes from socket %s, %u left.' % (got, transfer['socket'].fileno(), transfer['size'] - transfer['received']))
                    if transfer['size'] == transfer['received']:
                        transfer['socket'].close()
                        transfer['file'].close()
                        del self.transfers[sid]
                        try:
                            response = self.callback_file(transfer['from'], transfer['name'])
                        except Exception, e:
                            response = 'Could not process your file: %s: %s\n%s' % (e.__class__.__name__, e, traceback.format_exc(e))
                        if response is not None:
                            message = xmpp.protocol.Message(body=response)
                            message.setTo(transfer['from'])
                            message.setType('chat')
                            self.connect().send(message)
                        if os.path.exists(transfer['name']):
                            logging.debug('File not processed, removing.')
                            os.unlink(transfer['name'])
                        try:
                            os.rmdir(basename(transfer['name']))
                        except:
                            pass
                elif transfer['lastseen'] + self.SOCKET_TIMEOUT < int(time.time()):
                    logging.error('File %s from %s timed out.' % (transfer['name'], transfer['from']))
                    self.on_file_aborted(transfer)
                    del self.transfers[sid]

    def on_file_aborted(self, transfer):
        transfer['socket'].close()
        transfer['file'].close()
        os.unlink(transfer['name'])
