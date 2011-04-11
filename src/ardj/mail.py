# vim: set fileencoding=utf-8:

"""Interface to the mailbox.


"""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email
import email.header
import email.parser
import os
import poplib
import rfc822
import smtplib
import sys
import time
import urllib

# local modules
import ardj.settings
import ardj.util


USAGE = """Usage: ardj mail [command]

Commands:
  send addr [subject]   -- send message from stdin to addr
  list URL              -- show mail from that URL
"""

def parse_url(url):
    """Returns a dictionary with URL options.

    Something like urlparse.urlparse(), but supports login, password and port
    numbers."""
    try:
        scheme, rest = url.split('://', 1)
        auth, host = rest.rstrip('/').split('@', 1)
        login, password = auth.split(':', 1)
        server = host.split(':')[0]
        port = None
        if ':' in host:
            port = int(host.split(':')[1])
        return {
            'scheme': scheme,
            'login': urllib.unquote(login),
            'password': urllib.unquote(password),
            'server': server,
            'port': port,
        }
    except Exception, e:
        raise Exception('Could not parse URL: %s' % url)

class Message:
    """Simple message wrapper.

    Simplifies access to headers and attachments."""
    def __init__(self, client, number):
        """Initializes the message.

        Client is the POP3 or POP3_SSL client, used to retrieve messages and
        headers.  Number is the message number."""
        self.client = client
        self.number = number
        self.headers = None
        self.body = None

    def get_header(self, name, default=None):
        """Returns a particular header value."""
        return self.decode_header(self.get_headers()[name]) or default

    def get_addr(self, name, default=None):
        value = self.get_header(name, default)
        if value:
            return rfc822.parseaddr(value)
        return (None, None)

    def get_date(self):
        value = rfc822.parsedate(self.get_header('date'))
        if not value:
            value = time.localtime()
        return value

    def get_attachments(self, extensions=None):
        """Retrieves message attachments.

        Returns a list where each element is a tuple (file_name, contents)."""
        if self.body is None:
            self.headers = self.body = email.parser.Parser().parsestr('\n'.join(self.client.retr(self.number)[1]))

        result = []
        for i in self.body.walk():
            if i.is_multipart():
                continue
            if i.get_content_maintype() == 'text':
                continue
            att_name = self.decode_header(i.get_filename(None))
            if att_name:
                if extensions and os.path.splitext(att_name)[1].lower() not in extensions:
                    continue
                result.append((att_name, i.get_payload(decode=True)))
        return result

    def get_headers(self):
        """Returns all message headers."""
        if self.headers is None:
            self.headers = email.parser.Parser().parsestr('\n'.join(self.client.top(self.number, 0)[1]))
        return self.headers

    def decode_header(self, value):
        """Decodes the header value to Unicode."""
        if not value:
            return None
        decode_part = lambda x: x[1] and x[0].decode(x[1]) or x[0]
        value = u' '.join([decode_part(x) for x in email.header.decode_header(value)]).strip()
        return value.strip()

def send_mail(to, subject, message, files=None, profile=None):
    """Sends a message.

    The message is sent using SMTP settings from mail/smtp.

    Recipients are specified with the `to' parameter, `message' is the text
    part.  You can optionally attach files.
    
    Profile is the name of the mailbox in mail/boxes.  It can be used to use
    different smtp servers.  If not specified, the first smtp server is
    used."""
    if files and type(files) != list:
        files = [files]
    if type(to) != list:
        to = [to]

    if type(message) == unicode:
        message = message.encode('utf-8')

    msg = MIMEMultipart()
    msg.attach(MIMEText(message, _charset='utf-8'))

    if files:
        for filename in files:
            att = MIMEBase('application', 'octet-stream')
            attname = os.path.basename(filename)
            data = file(filename, 'rb').read()

            att.set_payload(data)
            encoders.encode_base64(att)
            att.add_header('content-disposition', 'attachment', filename=attname)
            msg.attach(att)

    try:
        if profile is None:
            profile = ardj.settings.get('mail/boxes').keys()[0]
        smtp = parse_url(ardj.settings.get('mail/boxes/%s/send' % profile))
    except:
        raise Exception('Could not find an SMTP profile.')

    login = smtp['login']
    password = smtp['password']

    msg['Subject'] = subject
    msg['To'] = to[0]
    if len(to) > 1:
        msg['Cc'] = ', '.join(to[1:])

    s = smtplib.SMTP(smtp['server'], int(smtp['port'] or '25'))
    s.ehlo()
    if smtp['scheme'] == 'smtps':
        s.starttls()
    s.ehlo()
    s.login(login, password)
    s.sendmail(login, to, msg.as_string())
    s.quit()

    ardj.log.info('Sent mail to %s' % to[0])

def process_mailbox(url, callback):
    """Process messages in a mailbox using a callback.

    Connects to the specified mailbox, retrieves messages and passes them to
    the callback, one by one.  If callback returns True, the message is deleted
    from the server.  The function itself returns True if at least one message
    was successfully processed.
    
    url is of the form pop3[s]://user:pass@host[:port].
    
    callback is a function which receives headers and a function which returns
    the whole message body.  To fetch attachments, use get_attachments()
    function."""
    if ':' not in url:
        rurl = url
        url = ardj.settings.get('mail/boxes/%s/fetch' % url)
        if url is None:
            raise Exception("Don't know how to read from mailbox \"%s\"." % rurl)

    params = parse_url(url)
    if params['scheme'] == 'pop3':
        client = poplib.POP3(params['server'])
    elif params['scheme'] == 'pop3s':
        client = poplib.POP3_SSL(params['server'])
    else:
        raise Exception("Don't know how to fetch mail from %s." % params['scheme'])

    client.user(params['login'])
    client.pass_(params['password'])

    result = expunge = False

    for msgid in client.list()[1]:
        number, length = msgid.split(' ', 1)
        try:
            if callback(Message(client, number)):
                client.dele(number)
                expunge = True
                ardj.log.debug('Deleted message %s from mailbox %s' % (number, params['login']))
            result = True
        except Exception, e:
            ardj.log.error('Could not process message: %s' % e)

    if expunge:
        client.quit()

    return result

def run_cli(args):
    """Implements the "ardj mail" command."""
    if len(args) > 1 and args[0] == 'send':
        args.append('no subject')
        return send_mail([args[1]], args[2], sys.stdin.read())
    if len(args) > 1 and args[0] == 'list':
        def callback(msg):
            print '- from: %s' % msg.get_header('from')
            print '    to: %s' % msg.get_header('to')
            print '  subj: %s' % msg.get_header('subject', 'no subject')
            for att in msg.get_attachments():
                print '  - file: %s (%u bytes)' % (att[0], len(att[1]))
            return False
        return process_mailbox(args[1], callback)
    print USAGE
