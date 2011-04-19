# vim: set fileencoding=utf-8:

"""Hotline interface.

Provides functions to list the mailbox and process incoming messages.

Uses the "hotline" mailbox, i.e. there should be a mail/boxes/hotline/fetch
parameter with an URL like pop3s://user:pass@host."""

import mutagen.mp3
import os
import time

import ardj.mail
import ardj.replaygain
import ardj.sms
import ardj.tags
import ardj.util
import ardj.website

# Files to upload as music.
upload_files = []

def display_message(msg, atts):
    """Prints key message informations."""
    phone = msg.get_header('x-asterisk-callerid')
    print '-  from: %s' % msg.get_header('from')
    print '   subj: %s' % msg.get_header('subject')
    if phone:
        print '    pbx: %s' % phone
    for att in atts:
        print '   file: %s (%u)' % (att[0], len(att[1]))


def list_messages(msg):
    """Displays a message.

    Only messages with audio attachments are displayed.  Messages are not
    deleted from the server.

    Used as a callback with ardj.mail.process_mailbox()."""
    atts = msg.get_attachments(extensions=('.mp3', '.wav', '.ogg', '.amr', '.flac', '.aiff'))
    if atts:
        display_message(msg, atts)
    return False


def transcode_file(filename):
    """Transcodes the file to MP3.

    Only does that if the file is not an MP3, not stereo or not 44100Hz.

    Returns the name of the new temporary file.
    """
    if str(filename).endswith('.mp3'):
        info = mutagen.mp3.Open(str(filename)).info
        if info.sample_rate == 44100 and info.mode != mutagen.mp3.MONO:
            return filename

    temp2 = ardj.util.mktemp(suffix='.mp3')
    ardj.util.run([ 'ffmpeg', '-i', str(filename), '-ar', '44100', '-ac', '2', '-y', str(temp2) ])

    return temp2

def mask_sender(sender):
    if sender.startswith('+') and sender[1:].isdigit():
        sender = sender[:-7] + 'XXX' + sender[8:]
    elif '@' in sender and ' ' not in sender:
        parts = sender.split('@', 1)
        parts[0] = parts[0][:-2] + '..'
        sender = '@'.join(parts)
    return sender

def process_messages(msg):
    """Processes a message.

    Only messages with audio attachments are displayed.  Messages are deleted
    from the server after (and only after) they're successfully added to the
    database.

    Used as a callback with ardj.mail.process_mailbox()."""
    atts = msg.get_attachments(extensions=('.mp3', '.wav', '.ogg', '.amr', '.flac', '.aiff'))
    if atts:
        full_sender = msg.get_addr('from')
        sender = full_sender[0] or full_sender[1]
        sender_id = full_sender[1]
        subject = msg.get_header('subject', 'no subject')
        date = msg.get_date()

        phone = msg.get_header('x-asterisk-callerid')
        if phone:
            sender_id = phone
            title = u'Сообщение от %s (%s)' % (mask_sender(phone), time.strftime('%Y-%m-%d %H:%M', date))
        else:
            title = u'%s: %s (%s)' % (mask_sender(sender), subject, time.strftime('%Y-%m-%d %H:%M', date))

        for filename, body in atts:
            temp = ardj.util.mktemp(suffix=os.path.splitext(filename)[1])
            open(str(temp), 'wb').write(body)

            temp = transcode_file(temp)
            ardj.replaygain.update(str(temp))

            labels = ardj.settings.get('hotline/labels', 'voicemail,hotline')
            if phone:
                labels += ',pbx'
            userlabels = ardj.settings.get('hotline/user_labels', {})
            if sender_id in userlabels:
                labels += ',' + userlabels[sender_id]

            ardj.tags.set(str(temp), {
                'artist': u'Горячая линия',
                'title': title,
                'ardj': 'ardj=1;labels=' + labels,
            })

            public_filename = time.strftime('%Y%m%d-%H%M%S.mp3', date)
            public_url = ardj.settings.get('hotline/download', fail=True).rstrip('/') + '/' + public_filename

            ardj.util.upload(temp, ardj.settings.get('hotline/upload', fail=True).rstrip('/') + '/' + public_filename)

            url = ardj.website.add_page('hotline/*/index.md', {
                'title': u'Сообщение от %s' % mask_sender(sender),
                'file': public_url,
                'filesize': str(os.stat(str(temp)).st_size),
                'labels': 'hotline',
                'date': time.strftime('%Y-%m-%d %H:%M:%S', date),
                'text': u'Сообщение получено по %s.' % (phone and u'телефону' or u'почте'),
            })

            if phone:
                ardj.sms.send(phone, 'Your message: %s' % url)
            elif full_sender[1]:
                ardj.mail.send_mail(full_sender[1], 'Your message received.', 'Find it here:\n%s' % url)

            global upload_files
            upload_files.append(temp)

            # show the tags to make sure they're ok
            #print ardj.tags.get(str(temp))
    return True


def run_cli(args):
    """Implements the "ardj hotline" command."""
    config = ardj.settings.get('mail/boxes/hotline/fetch')
    if config is None:
        if '-q' not in args:
            print 'Hotline is not configured (see mail/boxes/hotline/fetch).';
        return

    if args and args[0] == 'list':
        return ardj.mail.process_mailbox('hotline', list_messages)
    elif args and args[0] == 'process':
        if ardj.mail.process_mailbox('hotline', process_messages):
            ardj.website.update()
            ardj.util.upload_music(upload_files)
        return True
    print 'Usage: ardj hotline list|process'
