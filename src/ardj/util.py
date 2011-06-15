# encoding=utf-8

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib
import urllib2
import urlparse

import ardj.log
import ardj.replaygain
import ardj.settings
import ardj.util


def run(command, quiet=False, stdin_data=None, grab_output=False, nice=True):
    command = [str(x) for x in command]

    if nice:
        command = ['nice', '15'] + command

    if stdin_data is not None:
        filename = mktemp(suffix='.txt')
        open(str(filename), 'wb').write(stdin_data)
        command.append('<')
        command.append(str(filename))

    ardj.log.debug('> ' + ' '.join(command))
    stdout = stderr = None
    if quiet:
        stdout = stderr = subprocess.PIPE

    if grab_output:
        tmp_output = mktemp(suffix='.txt')
        stdout = open(str(tmp_output), 'wb')

    response = subprocess.Popen(command, stdout=stdout, stderr=stderr).wait() == 0
    if grab_output:
        response = file(str(tmp_output)).read()
    return response


class mktemp:
    def __init__(self, suffix=''):
        fd, self.filename = tempfile.mkstemp(prefix='ardj_', suffix=suffix)
        os.chmod(self.filename, 0664)
        os.close(fd)

    def __del__(self):
        if os.path.exists(self.filename):
            ardj.log.debug('Deleting temporary file %s' % self.filename)
            os.unlink(self.filename)

    def __str__(self):
        return self.filename

    def __unicode__(self):
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
    if args and not post:
        url += '?' + urllib.urlencode(args)

    opener = get_opener(url, user, password)
    try:
        u = opener(urllib2.Request(url), post and urllib.urlencode(args) or None)
        if post:
            ardj.log.info('Posting to %s' % url, quiet=quiet)
        else:
            ardj.log.info('Downloading %s' % url, quiet=quiet)
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
            ardj.log.error('Could not fetch %s: %s (retrying)' % (url, e))
            return fetch(url, suffix, args, user, password, quiet, post, ret, retry - 1)
        ardj.log.error('Could not fetch %s: %s' % (url, e))
        return None


def fetch_json(*args, **kwargs):
    data = fetch(*args, **kwargs)
    if data is not None:
        return json.loads(data)


def upload(source, target):
    """Uploads a file using SFTP."""
    if not os.path.exists(str(source)):
        raise Exception('Source file not found: %s' % source)

    upath = urlparse.urlparse(str(target))
    if upath.scheme == 'sftp':
        run([ 'scp', '-q', str(source), str(target)[5:].lstrip('/') ])
    else:
        raise Excepion("Don't know how to upload to %s." % upath.scheme)


def upload_music(filenames):
    """Uploads music files."""
    target = ardj.settings.get('database/upload')
    if not target:
        ardj.log.warning('Could not upload %u music files: database/upload not set.' % len(filenames))
        return False

    if type(filenames) != list:
        raise TypeError('filenames must be a list.')

    batch = mktemp(suffix='.txt')
    f = open(str(batch), 'wb')
    for fn in filenames:
        os.chmod(str(fn), 0664)
        f.write('put %s\n' % str(fn).replace(' ', '\\ '))
    f.close()

    return run([ 'sftp', '-b', str(batch), str(target) ])


def copy_file(src, dst):
    """Copies the file to a new location.

    Supports cross-device copy.
    
    If the target directory does not exist, it's created.
    """
    dirname = os.path.dirname(dst)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    shutil.copyfile(str(src), str(dst))
    ardj.log.debug('Copied %s to %s' % (src, dst))
    return True


def move_file(src, dst):
    """Moves the file to a new location.

    Supports cross-device copy.
    
    If the target directory does not exist, it's created.
    """
    dirname = os.path.dirname(dst)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    shutil.move(str(src), str(dst))
    ardj.log.debug('Moved %s to %s' % (src, dst))
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


def filemd5(filename):
    """Returns the file contents' MD5 sum (in hex)."""
    ardj.log.debug('Calculating MD5 of %s' % filename)
    m = hashlib.md5()
    f = open(filename, 'rb')
    while True:
        block = f.read(1024 * 1024)
        if not len(block):
            break
        m.update(block)
    return m.hexdigest()


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
    result = []
    for item in lst:
        if '-' in str(item):
            bounds = item.split('-')
            result += range(int(bounds[0]), int(bounds[1]))
        else:
            result.append(item)
    return result
