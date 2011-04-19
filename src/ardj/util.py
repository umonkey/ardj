# encoding=utf-8

import hashlib
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


def run(command, quiet=False, stdin_data=None):
    command = [str(x) for x in command]

    if stdin_data is not None:
        filename = ardj.util.mktemp(suffix='.txt')
        open(str(filename), 'wb').write(stdin_data)
        command.append('<')
        command.append(str(filename))

    ardj.log.debug('> ' + ' '.join(command))
    stdout = stderr = None
    if quiet:
        stdout = stderr = subprocess.PIPE

    return subprocess.Popen(command, stdout=stdout, stderr=stderr).wait() == 0


class mktemp:
    def __init__(self, suffix=''):
        self.filename = tempfile.mkstemp(prefix='ardj_', suffix=suffix)[1]
        os.chmod(self.filename, 0664)

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


def fetch(url, suffix=None, args=None, user=None, password=None, quiet=False, ret=False):
    """Retrieves a file over HTTP.

    Arguments:
    url -- the file to retrieve.
    suffix -- wanted, temporary file suffix (guessed if None)
    args -- a dictionary of query parameters
    user, password -- enable HTTP basic auth
    ret -- True to return file contents instead of a temporary file
    """
    if args:
        url += '?' + urllib.urlencode(args)

    opener = get_opener(url, user, password)
    u = opener(urllib2.Request(url))

    if u is not None:
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
        raise TypeError('duration must be a number')

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
