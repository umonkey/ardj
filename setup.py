#!/usr/bin/env python
# vim: set fileencoding=utf-8:

from glob import glob
from distutils.core import setup

# Files to install:
data_files = [
    #('/etc/cron.d', ['share/cron.d/ardj']),
    ('/etc/logrotate.d', glob('share/logrotate.d/*')),
    ('/etc/init', glob('share/upstart/*.conf')),
    ('share/doc/examples', glob('share/doc/ardj/examples/*')),
    ('share/ardj/database', glob('share/database/*.sql')),
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
    version = '0.13'
)
