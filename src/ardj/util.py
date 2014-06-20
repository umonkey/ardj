# encoding=utf-8

"""ARDJ, an artificial DJ.

This module contains various utility functions.
"""

import hashlib
import json
import logging
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import urllib
import urllib2
import urlparse

import ardj.replaygain
from ardj import settings
import ardj.util


class ProgramNotFound(Exception):
    pass


def edit_file(filename):
    editor = os.getenv("EDITOR", "editor")
    subprocess.Popen([editor, filename]).wait()


def run_ex(command, quiet=False, stdin_data=None, grab_output=False, nice=True):
    command = [str(x) for x in command]

    if not os.path.exists(command[0]) and not is_command(command[0]):
        raise ProgramNotFound("Please install the %s program first." % command[0])

    if nice:
        command = ['nice', '-n15'] + command

    logging.debug('> ' + ' '.join(command))
    stdout = stderr = None
    if quiet:
        stdout = stderr = subprocess.PIPE

    if grab_output:
        tmp_output = mktemp(suffix='.txt')
        stdout = open(str(tmp_output), 'wb')

    _cmd = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
    out, err = _cmd.communicate(stdin_data)
    return _cmd.returncode, out, err


def run(*args, **kwargs):
    status, out, err = run_ex(*args, **kwargs)

    response = status == 0
    if kwargs.get("grab_output"):
        response = out
    return response


def is_command(name):
    """Checks whether the named program exists, returns True on success."""
    for folder in os.getenv("PATH").split(os.pathsep):
        filename = os.path.join(folder, name)
        if os.path.exists(filename):
            return True
    return False


class mktemp:
    """This class is used to deal with temporary files which should be deleted
    automatically.  When all references to an instance are deleted, the
    underlying file is unlinked from the file system.

    Usage is simple:

    from ardj.util import mktemp
    print str(mktemp(suffix=".log"))

    Be sure to convert the value to a string, otherwise most receivers will
    fail (got object while expected a string, or something)."""
    def __init__(self, suffix=''):
        """Creates a new file in the temporary folder using tempfile.mkstemp().
        Files have a fixed prefix "ardj_" and a custom suffix, none by
        default."""
        fd, self.filename = tempfile.mkstemp(prefix='ardj_', suffix=suffix)
        os.chmod(self.filename, 0664)
        os.close(fd)

    def __del__(self):
        """Deletes the temporary file if it still exists."""
        if os.path.exists(self.filename):
            logging.debug('Deleting temporary file %s' % self.filename)
            os.unlink(self.filename)

    def __str__(self):
        """Returns the name of the file."""
        return self.filename

    def __unicode__(self):
        """Returns the Unicode version of the name of the file (does not differ from str)."""
        return unicode(self.filename)


def get_opener(url, user, password):
    """Returns an opener for the url.

    Builds a basic HTTP auth opener if necessary."""
    opener = urllib2.urlopen

    if user or password:
        pm = urllib2.HTTPPasswordMgrWithDefaultRealm()
        pm.add_password(None, url, user, password)

        ah = urllib2.HTTPBasicAuthHandler(pm)
        opener = urllib2.build_opener(ah).open

    return opener


def fetch(url, suffix=None, args=None, user=None, password=None, quiet=False, post=False, ret=False, retry=3):
    """Retrieves a file over HTTP.

    Arguments:
    url -- the file to retrieve.
    suffix -- wanted, temporary file suffix (guessed if None)
    args -- a dictionary of query parameters
    user, password -- enable HTTP basic auth
    ret -- True to return file contents instead of a temporary file
    """
    if type(url) != str:
        raise TypeError("URL must be a string.")

    if args and not post:
        url += '?' + urllib.urlencode(args)

    url, user, password = parse_url_auth(url, user, password)

    opener = get_opener(url, user, password)
    try:
        if post:
            logging.debug('Posting to %s' % url)
            u = opener(urllib2.Request(url), urllib.urlencode(args))
        else:
            logging.debug('Downloading %s' % url)
            u = opener(urllib2.Request(url), None)
        if ret:
            return u.read()
        if suffix is None:
            suffix = os.path.splitext(url)[1]
        filename = mktemp(suffix=suffix)
        out = open(str(filename), 'wb')
        out.write(u.read())
        out.close()
        if os.path.splitext(str(filename).lower()) in ('.mp3', '.ogg', '.flac'):
            ardj.replaygain.update(str(filename))
        return filename
    except Exception, e:
        if retry:
            logging.error('Could not fetch %s: %s (retrying)' % (url, e))
            return fetch(url, suffix, args, user, password, quiet, post, ret, retry - 1)
        logging.error('Could not fetch %s: %s' % (url, e))
        return None


def parse_url_auth(url, user, password):
    """Extracts auth parameters from the url."""
    up = urlparse.urlparse(url)

    netloc = up.netloc
    if "@" in up.netloc:
        auth, netloc = up.netloc.split("@", 1)
        user, password = list(auth.split(":", 1) + [password])[:2]

    result = "%s://%s%s" % (up.scheme, netloc, up.path)
    if up.query:
        result += "?" + up.query
    return result, user, password


def fetch_json(*args, **kwargs):
    """Fetches the data using fetch(), parses it using the json module, then
    returns the result."""
    data = fetch(*args, **kwargs)
    if data is not None:
        return json.loads(data)


def upload(source, target):
    """Uploads a file using SFTP."""
    if not os.path.exists(str(source)):
        raise Exception('Source file not found: %s' % source)

    upath = urlparse.urlparse(str(target))
    if upath.scheme == 'sftp':
        run(['scp', '-q', str(source), str(target)[5:].lstrip('/')])
    else:
        raise Excepion("Don't know how to upload to %s." % upath.scheme)


def upload_music(filenames):
    """Uploads music files."""
    target = settings.get('database/upload')
    if not target:
        logging.warning('Could not upload %u music files: database/upload not set.' % len(filenames))
        return False

    if type(filenames) != list:
        raise TypeError('filenames must be a list.')

    batch = mktemp(suffix='.txt')
    f = open(str(batch), 'wb')
    for fn in filenames:
        os.chmod(str(fn), 0664)
        f.write('put %s\n' % str(fn).replace(' ', '\\ '))
    f.close()

    return run(['sftp', '-b', str(batch), str(target)])


def copy_file(src, dst):
    """Copies the file to a new location.

    Supports cross-device copy.

    If the target directory does not exist, it's created.
    """
    dirname = os.path.dirname(dst)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    shutil.copyfile(str(src), str(dst))
    logging.debug('Copied %s to %s' % (src, dst))
    return True


def move_file(src, dst):
    """Moves the file to a new location.

    Supports cross-device copy.

    If the target directory does not exist, it's created.
    """
    dirname = os.path.dirname(dst)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    try:
        shutil.move(str(src), str(dst))
    except OSError, e:
        if "Operation not permitted" not in str(e):
            raise e

    logging.debug('Moved %s to %s' % (src, dst))
    return True


def format_duration(duration, age=False, now=None):
    if not str(duration).isdigit():
        raise TypeError('duration must be a number, not "%s"' % duration)

    duration = int(duration)
    if age:
        if not duration:
            return 'never'
        duration = int(now or time.time()) - duration
    parts = ['%02u' % (duration % 60)]
    duration /= 60
    if duration:
        parts.insert(0, '%02u' % (duration % 60))
        duration /= 60
        if duration:
            parts.insert(0, str(duration))
    result = ':'.join(parts)
    if len(parts) > 1:
        result = result.lstrip('0')
    if age:
        result += ' ago'
    return result


def mask_sender(sender):
    if sender.startswith('+') and sender[1:].isdigit():
        sender = sender[:-7] + 'XXX' + sender[8:]
    elif '@' in sender and ' ' not in sender:
        parts = sender.split('@', 1)
        if len(parts[0]) >= 6:
            parts[0] = parts[0][:-2] + '..'
        elif len(parts[1]) > 6:
            parts[1] = '..' + parts[1][2:]
        sender = '@'.join(parts)
    return sender


def lower(s):
    if type(s) == str:
        s = s.decode('utf-8')
    return s.lower().replace(u'ё', u'е')


def ucmp(a, b):
    return cmp(lower(a), lower(b))


def in_list(a, lst):
    for i in lst:
        if not ucmp(i, a):
            return True
    return False


def shortlist(items, limit=3, glue='and'):
    if len(items) == 1:
        return items[0]

    if len(items) <= limit:
        last = items[-1]
        del items[-1]
        return '%s %s %s' % (', '.join(items), glue, last)

    return u', '.join(items[:limit]) + u' and %u more' % (len(items) - limit)


def expand(lst):
    """Expands ranges specified in the list.  For example, this:

    ["1", "3-5", "7"]

    Is expanded to:

    ["1", "3", "4", "5", "7"]

    This function is usually actively used in the playlists.
    """
    result = []
    for item in lst:
        if '-' in str(item):
            bounds = item.split('-')
            result += range(int(bounds[0]), int(bounds[1]))
        else:
            result.append(item)
    return result


def shorten_url(url):
    """Returns a shortened version of an URL."""
    try:
        new_url = fetch("http://clck.ru/--", args={"url": url}, ret=True)
        if len(new_url) >= len(url):
            new_url = url
        else:
            logging.debug("URL %s shortened to %s" % (url, new_url))
        return new_url
    except Exception, e:
        logging.error("Could not shorten an URL: %s" % e)
        return url


def shorten_urls(message):
    """Returns the message with all urls shortened."""
    output = []
    for word in re.split("\s+", message):
        if word.startswith("http://"):
            word = shorten_url(word)
        output.append(word)
    return u" ".join(output)


def signal_by_pid_file(filename, sig):
    """
    Send a signal to a process listed in a pid file.

    Returns True on success, False on failure.
    """
    path = os.path.join(settings.get_config_dir(), filename)
    if not os.path.exists(path):
        return False

    try:
        with open(path, "rb") as f:
            pid = int(f.read().strip())
            os.kill(pid, sig)
            return True
    except Exception, e:
        logging.exception("Error skipping track.")
        return False


def skip_current_track():
    """Sends a skip request to the appropriate source client."""
    if not signal_by_pid_file("ezstream.pid", signal.SIGUSR1):
        if not signal_by_pid_file("ices.pid", signal.SIGUSR1):
            raise Exception("Could not skip track: no valid pid files.")
    return True


def shorten_file_path(filepath):
    musicdir = settings.get_music_dir()
    filepath = os.path.realpath(filepath)
    if filepath.startswith(musicdir):
        return filepath[len(musicdir) + 1:]
    return filepath


def shared_file(name):
    paths = ["/usr/share/ardj",
        "/usr/local/share/ardj",
        "share"]

    tmp = os.getenv("VIRTUAL_ENV")
    if tmp:
        paths.append(tmp)

    for path in paths:
        dst = os.path.join(path, name)
        if os.path.exists(dst):
            return dst


def find_sample_music():
    """Returns files to pre-seed the media database with."""
    return [f for f in [
        shared_file("audio/cubic_undead.mp3"),
        shared_file("audio/successful_install.ogg"),
    ] if f]
