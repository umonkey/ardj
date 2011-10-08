#!/usr/bin/env python
# vim: set fileencoding=utf-8:

from distutils.core import setup
from glob import glob
import os

# Files to install:
data_files = [
    #('/etc/cron.d', ['share/cron.d/ardj']),
    ('/etc/logrotate.d', glob('share/logrotate.d/*')),
    ('/etc/init', glob('share/upstart/*.conf')),
    ('share/doc/ardj/examples', glob('share/doc/ardj/examples/*')),
    ('share/ardj/database', glob('share/database/*.sql')),
    ('share/ardj/failure', ['share/audio/stefano_mocini_leaving_you_failure_edit.ogg']),
    ('share/ardj/samples', ['share/audio/cubic_undead.mp3', 'share/audio/successful_install.ogg']),
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
    version = os.environ.get("VERSION", "1.0.1")
)
