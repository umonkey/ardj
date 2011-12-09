#!/usr/bin/env python
# vim: set fileencoding=utf-8 tw=0:

import email
import email.header
import email.parser
import logging
import logging.handlers
import os
import re
import rfc822
import subprocess
import sys
import tempfile
import time
import traceback
import urllib

try:
    import imaplib2 as imaplib
    HAVE_IDLE = True
except ImportError:
    import imaplib
    HAVE_IDLE = False

import mad
import mutagen.easyid3
import yaml


CONFIG_NAMES = ["~/.config/hotline.yaml", "/etc/hotline.yaml"]

fn_filter = re.compile('wav|mp3|ogg', re.I)

mutagen.easyid3.EasyID3.RegisterTXXXKey('ardj', 'ardj')


def log_error(e, message):
    message += "\n" + traceback.format_exc(e)
    for line in message.strip().split("\n"):
        logging.error(line)


def config_get(key, default=None):
    """Returns a value from the config file.  The file is read on every call,
    which is OK because the traffic is unlikely that heavy, and you get instand
    updates without reloading the daemon."""
    for fn in CONFIG_NAMES:
        fn = os.path.expanduser(fn)
        if os.path.exists(fn):
            data = yaml.load(file(fn, "rb").read())
            return data.get(key, default)
    return default


def install_syslog():
    """Makes use of the syslog."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    syslog = logging.handlers.SysLogHandler(address="/dev/log")
    syslog.setLevel(logging.DEBUG)

    format_string = "hotline[%(process)d]: %(levelname)s %(message)s"
    formatter = logging.Formatter(format_string)
    syslog.setFormatter(formatter)

    logger.addHandler(syslog)


def install_file_logger(filename):
    """Adds a custom formatter and a rotating file handler to the default
    logger."""
    folder = os.path.dirname(filename)
    if not os.path.exists(folder) or not os.access(folder, os.W_OK):
        raise Exception("Can't log to %s: no write permissions." % filename)

    max_size = 1000000
    max_count = 5

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    h = logging.handlers.RotatingFileHandler(filename, maxBytes=max_size, backupCount=max_count)

    h.setFormatter(logging.Formatter('%(asctime)s - %(process)6d - %(levelname)s - %(message)s'))
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)


def message_has_audio(num, headers):
    """
    match = fn_filter.search(headers)
    if match is None:
        logging.debug("Message does not match: %s" % headers)
        return False
    """

    #logging.debug("Message %s has an audio file." % num)
    return True


def run(cmd, wait=True):
    cmd.insert(0, "nice")
    cmd.insert(1, "-n15")
    logging.debug("Running a command: %s" % " ".join(cmd))
    tmp = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if wait:
        tmp.wait()


def transcode(filename, body):
    logging.debug("Transcoding %s to MP3." % filename)

    tmp_name = wav_name = mp3_name = None

    try:
        tmp_name = tempfile.mktemp(suffix=os.path.splitext(filename)[1].lower())
        file(tmp_name, "wb").write(body)
        logging.debug("Wrote data to %s" % tmp_name)

        if tmp_name.endswith(".mp3"):
            mf = mad.MadFile(tmp_name)
            if mf.mode() != mad.MODE_SINGLE_CHANNEL and mf.samplerate() == 44100:
                logging.debug("File %s does not need transcoding." % filename)
                os.unlink(tmp_name)
                return body

        wav_name = tempfile.mktemp(suffix=".wav")
        run(["sox", "-q", tmp_name, "-r", "44100", "-c", "2", "-s", wav_name])
        logging.debug("Transcoded %s to %s" % (tmp_name, wav_name))

        mp3_name = tempfile.mktemp(suffix=".mp3")
        run(["lame", "--quiet", "--preset", "extreme", wav_name, mp3_name])
        run(["mp3gain", "-q", mp3_name])
        logging.debug("Transcoded %s to %s" % (wav_name, mp3_name))

        body = file(mp3_name, "rb").read()

        return body
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)
        if wav_name:
            os.unlink(wav_name)
        if mp3_name:
            os.unlink(mp3_name)


def set_tags(filename, artist, date):
    tags = mutagen.easyid3.EasyID3()
    tags["artist"] = artist
    tags["title"] = time.strftime("%d.%m.%y %H:%M", date)
    tags["ardj"] = "ardj=1;labels=hotline"
    tags.save(filename)

    logging.debug("Wrote ID3 tags to %s" % filename)


def mask_sender(name, addr, phone):
    if phone:
        phone_map = config_get("phone_map", {})
        return phone_map.get(phone, phone[:-7] + "XXX" + phone[-4:])

    addr_map = config_get("email_map", {})
    if addr in addr_map:
        return addr_map[addr]

    return name


def process_file(name, body, sender_name, sender_addr, sender_phone, date):
    logging.debug("Incoming file: sender_name=%s sender_addr=%s sender_phone=%s" % (sender_name.encode("utf-8"), sender_addr.encode("utf-8"), sender_phone))

    sender = mask_sender(sender_name, sender_addr, sender_phone)

    logging.debug("%s (%s) sent a file: %s (%u bytes)" % (sender.encode("utf-8"), sender_addr.encode("utf-8"), name, len(body)))

    body = transcode(name, body)

    name = time.strftime(config_get("mp3_file_name", "/tmp/%Y-%m-%d-hotline-%H%M.mp3"), date)
    if os.path.exists(name):
        logging.warning("File %s already exists, skipping." % name)
        return False

    file(name, "wb").write(body)
    logging.info("Message from %s saved as %s" % (sender.encode("utf-8"), name))

    duration = int(mad.MadFile(name).total_time() / 1000)
    if duration < int(config_get("min_duration", 0)):
        logging.warning("Message is too short, skipped.")
        return False
    if duration > int(config_get("max_duration", 3600)):
        logging.warning("Message is too long, skipped.")
        return False

    set_tags(name, sender, date)

    page_name = time.strftime(config_get("page_name", "/tmp/%Y-%m-%d-hotline-%H%M.md"), date)
    if page_name:
        page = u"title: Горячая линия: %(sender)s\ndate: %(date)s\nlabels: podcast, hotline\nfile: %(url)s\nfilesize: %(size)s\nduration: %(duration)u\n---\nNo description." % {
            "sender": sender,
            "date": time.strftime("%Y-%m-%d %H:%M:%S", date),
            "url": time.strftime(config_get("mp3_file_url", "http://example.com/files/%Y-%m-%d-hotline-%H%M.mp3"), date),
            "size": os.stat(name).st_size,
            "duration": duration,
        }

        page_dir = os.path.dirname(page_name)
        if not os.path.exists(page_dir):
            os.makedirs(page_dir)

        file(page_name, "wb").write(page.encode("utf-8"))
        logging.info("Wrote %s" % page_name)

    return True


def decode_value(value):
    for part in re.findall("(=(?:\?[^?]+){3}\?=)", value):
        repl = u""
        for _t, _e in email.header.decode_header(part):
            if _e is None:
                repl += unicode(_e)
            else:
                repl += _t.decode(_e)
        value = value.replace(part, repl)
    return value


def decode_file_name(encoded):
    """File names can contain all sorts of garbage, so we decode it, but only
    use the extension."""
    if encoded is not None:
        ext = decode_value(encoded).split(".")[-1]
        return "tmp." + ext


def decode_sender(sender):
    """Decode UTF-8 base64 etc headers.  decode_header() must be able to do
    this on its own, but due to a bug it fails to process multiline values."""
    sender = decode_value(sender)
    return rfc822.parseaddr(sender.replace("\r\n", ""))


def get_phone_number(msg):
    """Extracts caller's phone number from the headers."""
    tmp = re.search("(\d+)", msg["X-WUM-FROM"] or "")
    if tmp:
        number = tmp.group(1)
        if number.startswith("8"):
            number = number[1:]
        if not number.startswith("+"):
            number = "+7" + number
        return number

    tmp = msg["X-Asterisk-CallerID"]
    if tmp:
        return tmp

    return None


def download_message(mail, data):
    msg = email.message_from_string(data)

    logging.debug("Message-ID is %s" % msg["Message-ID"])

    sender_name, sender_addr = decode_sender(msg.get_all("From")[0])
    sender_phone = get_phone_number(msg)
    date = rfc822.parsedate(msg["Date"])

    status = False
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get("Content-Disposition") is None:
            continue
        name = decode_file_name(part.get_filename())
        if name is None:
            logging.debug("Message part has no name, skipped.")
            continue
        data = part.get_payload(decode=True)
        if process_file(name, data, sender_name, sender_addr, sender_phone, date):
            status = True

    return status


def check_one_message(mail, num):
    status = False

    logging.debug("Checking message %s." % num)

    result, data = mail.uid("fetch", num, "(BODY)")
    if result != "OK":
        return False

    if message_has_audio(num, data[0]):
        logging.debug("Fetching message %s" % num)
        result, data = mail.uid("fetch", num, "(RFC822)")
        if result == "OK":
            if download_message(mail, data[0][1]):
                status = True

    return status


def search_messages(mail):
    have_new_messages = False

    logging.debug("Searching for new messages.")

    debug_num = config_get("imap_debug_message")
    if debug_num:
        message_ids = [str(debug_num)]
    else:
        result, data = mail.uid("search", "(UNSEEN)")
        if result != "OK":
            return False
        message_ids = data[0].split()

    for num in message_ids:
        try:
            if check_one_message(mail, num):
                have_new_messages = True
        except Exception, e:
            log_error(e, "Error checking message %s: %s" % (num, e))

    if have_new_messages:
        fn = config_get("postprocessor", "/bin/true")
        run(fn.split(" "), wait=False)
    else:
        logging.debug("No new messages were found.")


def connect_and_wait():
    server = config_get("imap_server")
    logging.info("Connecting to %s" % server)
    mail = imaplib.IMAP4_SSL(server)
    mail.login(config_get("imap_user"), config_get("imap_password"))
    mail.select(config_get("imap_folder", "INBOX"))

    # Maybe there's something already.
    search_messages(mail)

    if config_get("imap_debug_message"):
        mail.logout()
        exit(0)

    while HAVE_IDLE:
        mail.idle()
        search_messages(mail)


def loop():
    while True:
        try:
            connect_and_wait()
        except KeyboardInterrupt:
            logging.info("Interrupted by user.")
            return
        except Exception, e:
            log_error(e, "ERROR: %s, restarting in 5 seconds." % e)
            time.sleep(5)

        logging.debug("Sleeping for 60 seconds.")
        time.sleep(60)


install_syslog()
install_file_logger("/radio/logs/hotline.log")

loop()
