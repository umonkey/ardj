import os
import shutil
import subprocess
import sys
import tempfile
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

def fetch(url, suffix=None, ret=False):
    u = urllib2.urlopen(urllib2.Request(url))
    if u is not None:
        if ret:
            return u.read()
        ardj.log.info('Downloading %s' % url)
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
    return run([ 'scp', '-q', [str(x) for x in filenames], target])

def move_file(src, dst):
    """Moves file src to dst.

    Supports cross-device links."""
    return shutil.move(str(src), str(dst))
