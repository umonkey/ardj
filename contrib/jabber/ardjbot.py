#!/usr/bin/env python
# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import sys

try:
	import yaml
except ImportError:
	print >>sys.stderr, 'Please install PyYAML (python-yaml).'
	sys.exit(13)

from jabberbot import *

class ardjbot(JabberBot):
	def __init__(self, config_name):
		self.folder = os.path.dirname(config_name)
		if not os.path.exists(config_name):
			raise Exception('Config file not found: %s' % config_name)
		config = yaml.load(open(config_name, 'r').read())
		try:
			u, password = config['jabber']['login'].split('@')[0].split(':')
			h = config['jabber']['login'].split('@')[1]
			login = u + '@' + h
			self.users = config['jabber']['access']
			print self.users
		except KeyError:
			raise Exception('Not enough parameters in config.')
		except:
			raise Exception('Incorrect login info, must be user:pass@host.')
		JabberBot.__init__(self, login, password)

	def get_current(self):
		shortlog = os.path.join(self.folder, 'ardj.short.log')
		if not os.path.exists(shortlog):
			raise Exception('Short log file not found.')
		return open(shortlog, 'r').read().split('\n')[0].split(' ', 2)[2]

	def check_access(self, message):
		return message.getFrom().split('/')[0] in self.users

	def callback_message(self, conn, mess):
		if mess.getType() == 'chat':
			if mess.getFrom().getStripped() not in self.users:
				return self.send_simple_reply(mess, 'No access for you.')
		return JabberBot.callback_message(self, conn, mess)

	@botcmd
	def name(self, message, args):
		"see what's being played now."
		return self.get_current()

	@botcmd
	def delete(self, message, args):
		"delete a file (provided a file name)."
		if not args:
			return 'Usage: delete filename. You can find the name using command "name".'
		if args == 'current':
			args = self.get_current()
		filename = os.path.join(self.folder, args.strip())
		if not os.path.exists(filename):
			return 'File "%s" does not exist.' % filename
		os.rename(filename, filename + '.deleted')
		return 'File "%s" was removed from the playlist.' % filename

def run(settings):
    if settings['jabber'] is None:
        print >>sys.stderr, 'No jabber settings (jabber.login, jabber.password)'
        sys.exit(1)
    bot = FMHBot(settings['jabber']['login'], settings['jabber']['password'])
    bot.serve_forever()

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print >>sys.stderr, 'Usage: %s path/to/ardj.yaml' % sys.argv[0]
		sys.exit(1)

	try:
		bot = ardjbot(sys.argv[1])
	except Exception, e:
		print >>sys.stderr, e
		sys.exit(1)

	while True:
		try:
			bot.serve_forever()
			sys.exit(0)
		except Exception, e:
			print >>sys.stderr, 'Error: %s, restarting' % e
