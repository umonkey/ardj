#!/usr/bin/env python
# vim: set fileencoding=utf-8:
#
# Retrieves messages from a mailbox, retrieves attachments and passes them to
# an external program.  Designed to be set up as a cron job.
#
# Reads ~/.config/tmradio/voicemail.conf of the following format:
#
#     --- 8< ---
#     host: pop.gmail.com
#     login: john.doe
#     password: secret
#     to: john.doe+voice@gmail.com
#     files: \.amr$
#     command: ./voicemail.sh
#     --- 8< ---
#
# With these settings the script will connect to the mailbox for user john.doe
# at Gmail, find all messages addressed to john.doe+voice@gmail.com, extract
# *.amr files and pass them to the ./voicemail.sh command.
#
# If you want to only process messages that have a certain word in the subject
# line, define it as "subject: keyword".
#
# Don't forget to chmod 600 voicemail.conf after you create it, as it contains
# your mailbox password.
#
# To add intro and outro, create files voicemail-pre.wav and voicemail-post.wav
# in ~/.config/tmradio, also make sure that sox is installed (it's used to
# concat sound files).

import email.header
import email.parser
import email.utils
import logging
import logging.handlers
import os
import poplib
import re
import rfc822
import subprocess
import sys
import tempfile
import traceback
import yaml

log = None
settings = None


def exec_command(filename, sender, subject):
    """Выполняет внешнюю программу, передавая ей имя файла.
    """
    if not settings.has_key('command'):
        raise Exception('External command not configured.')
    if type(filename) == unicode:
        filename = filename.encode('utf-8')
    if type(subject) == unicode:
        subject = subject.encode('utf-8')
    try:
        log.info(u'Running %s for file "%s" received from %s with subject: %s' % (settings['command'], filename, sender, subject))
    except Exception, e:
        log.info('WTF :(')
    res = subprocess.Popen([settings['command'], filename, sender, subject]).wait()
    if res:
        raise Exception('External command failed.')


def parse(headers):
    """Parses headers, returns a Message instance."""
    return email.parser.Parser().parsestr('\n'.join(headers))


def check_message(headers):
    """Check if a message should be posted.

    Returns True if the message is directed to the right destination
    and contains a marker in the subject line.
    """
    headers = parse(headers)
    if settings['to'] not in headers['to']:
        log.debug('Recipient mismatch: %s instead of %s' % (headers['to'], settings['to']))
        return False
    if settings.has_key('subject') and settings['subject'] not in headers['subject']:
        log.debug('Subject mismatch: must have "%s" in it, got: %s' % (settings['subject'], headers['subject']))
        return False
    return True


def decode_subject(header):
    decode_part = lambda x: x[1] and x[0].decode(x[1]) or x[0]
    subject = u' '.join([decode_part(x) for x in email.header.decode_header(header)]).strip()
    if settings is not None and settings.has_key('subject'):
        subject = subject.replace(settings['subject'], '')
    # some shell protection
    subject = subject.replace('`', "'")
    return subject.strip()


def decode_attachment(encoding, content):
    """Возвращает декодированное содержимое файла.

    Параметр encoding содержит значение заголовка Content-Transfer-Encoding
    (обычно base64), content — закодированное содержимое файла.
    """
    if encoding.lower() == 'base64':
        return email.base64mime.body_decode(content)
    raise Exception('Unknown transfer encoding: %s' % encoding)


def get_att_name(att):
    tmp = email.header.decode_header(att.get_filename())
    filename = tmp[0][0]
    if tmp[0][1] is not None:
        filename = filename.decode(tmp[0][1])
    return filename



def get_attachments(message):
    """Возвращает список вложений.

    Если вложений нет, список будет пустым.
    """
    result = []

    r = None
    if settings.has_key('files'):
        r = re.compile(settings['files'])

    payload = message.get_payload()
    if type(payload) == list:
        for att in payload:
            filename = get_att_name(att)
            if r is None or r.search(filename.lower()):
                data = decode_attachment(att['content-transfer-encoding'], att.get_payload())
                if data:
                    filepath = os.path.join(tempfile.gettempdir(), filename)
                    result.append((filepath, data, ))
    return result


def process_message(message):
    sender = rfc822.parseaddr(message['from'])[1]
    subject = decode_subject(message['subject'])

    attachments = get_attachments(message)
    log.info('Got a message from %s, %u files, subject: %s' % (sender, len(attachments), subject))

    for filepath, data in attachments:
        f = open(filepath, 'wb')
        f.write(data)
        f.close()
        exec_command(filepath, sender, subject)
        os.unlink(filepath)


def get_client():
    global settings
    client = poplib.POP3_SSL(settings['host'])
    client.user(settings['login'])
    client.pass_(settings['password'])
    return client

def fetch_messages(client):
    messages = client.list()[1]
    if not len(messages):
        log.debug('No mail.')
    return messages

def scan_mailbox():
    """Reads and processes the mailbox.

    Connects to the mailbox specified in the settings, analyzes all messages,
    retrieves the ones that match and posts them as blog entries (creates
    the necessary files, should be committed separately).
    """
    client = get_client()
    for msgid in fetch_messages(client):
        try:
            number, length = msgid.split(' ', 1)
            if check_message(client.top(number, 0)[1]):
                log.debug('Found a message: %s.' % msgid)
                process_message(parse(client.retr(number)[1]))
                client.dele(number)
        except Exception, e:
            traceback.print_exc(e)
            log.error('ERROR processing a message (%s): %s.' % (msgid, e))
            sys.exit(1) # prevents expunge
    client.quit()

def init():
    global settings
    for filename in ('~/.config/tmradio.conf', '/etc/tmradio.conf'):
        filename = os.path.expanduser(filename)
        if os.path.exists(filename):
            config = yaml.load(open(filename, 'rb'))
            if config.has_key('voicemail'):
                settings = { 'log': 'voicemail.log' }
                settings.update(config['voicemail'])
                init_logging()
                return

    raise Exception('Could not find a config file.')

def init_logging():
    global log
    log = logging.getLogger('voicemail')
    log.setLevel(logging.DEBUG)

    h = logging.handlers.RotatingFileHandler(settings['log'], maxBytes=1000000, backupCount=5)
    h.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    h.setLevel(logging.DEBUG)
    log.addHandler(h)

if __name__ == '__main__':
    # Go to the script folder.
    os.chdir(os.path.dirname(os.path.realpath(sys.argv[0])))

    init()
    scan_mailbox()
