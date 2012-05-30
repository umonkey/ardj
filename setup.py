#!/usr/bin/env python
# vim: set fileencoding=utf-8:

from distutils.core import setup
from glob import glob
import os
import sys


def glob_files(pattern):
    return [f for f in glob(pattern) if os.path.isfile(f)]

# Files to install:
data_files = [
    ('/etc', ['share/doc/examples/ardj.yaml', 'share/ezstream.xml']),
    ('/etc/cron.d', ['share/cron.d/ardj']),
    ('/etc/logrotate.d', glob_files('share/logrotate.d/*')),
    ('/etc/rsyslog.d', glob_files('share/rsyslog.d/*')),
    #('/etc/sudoers.d', glob_files('share/sudoers.d/*')),
    ('/usr/share/ardj/database', glob_files('share/database/*.sql')),
    ('/usr/share/ardj/failure', ['share/audio/stefano_mocini_leaving_you_failure_edit.ogg']),
    ('/usr/share/ardj/samples', ['share/audio/cubic_undead.mp3', 'share/audio/successful_install.ogg']),
    ('/usr/share/ardj/shell-extensions/zsh', ['share/shell-extensions/zsh/_ardj']),
    ('/usr/share/doc/ardj/examples', glob_files('share/doc/examples/*')),
    ('/usr/share/doc/ardj/examples/sysvinit', glob_files('share/init.d/*')),
    ('/usr/share/doc/ardj/examples/upstart', glob_files('share/upstart/*.conf')),
    ('/usr/share/doc/ardj/html/', glob_files('docbook/chunked/*')),
    ('/usr/share/man/man1', ['share/doc/man/ardj.1.gz']),
    ('/usr/lib/ardj', ['bin/ardj-next-track', 'bin/ezstream-meta', 'bin/config']),
]

classifiers = [
    'License :: OSI Approved :: GNU General Public License (GPL)',
    'Natural Language :: English',
    'Operating System :: Unix',
    'Programming Language :: Python',
    'Topic :: Internet',
    ]

setup(
    author = 'Justin Forest',
    author_email = 'hex@umonkey.net',
    classifiers = classifiers,
    data_files = data_files,
    description = 'An artificial DJ for you internet radio.',
    long_description = 'An artificial DJ for your icecast2 based internet radio.  Consists of an ices python playlist module and a jabber bot which lets you control that radio.  Supports sending messages to twitter and other unnecessary stuff.',
    license = 'GNU GPL',
    name = 'ardj',
    package_dir = { '': 'src' },
    packages = [ 'ardj', 'ardj.xmpp' ],
    requires = [ 'yaml', 'mutagen', 'dns', 'socksipy', 'simplejson', 'oauth2' ],
    scripts = [ 'bin/ardj' ],
    url = 'http://ardj.googlecode.com/',
    version = '1.0.12'
)
