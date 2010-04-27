#!/usr/bin/env python
# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import sys
import traceback
import xmpp

try:
	import yaml
except ImportError:
	print >>sys.stderr, 'Please install PyYAML (python-yaml).'
	sys.exit(13)

try:
	import pyinotify
except ImportError:
	print >>sys.stderr, 'Please install pyinotify.'
	sys.exit(13)

try:
	import mutagen
	import mutagen.easyid3
except ImportError:
	print >>sys.stderr, 'Pleasy install python-mutagen.'
	sys.exit(13)

from jabberbot import *

def get_file_tags(filename):
	if filename.lower().endswith('.mp3'):
		return mutagen.easyid3.Open(filename)
	return mutagen.File(filename)

class LogNotifier(pyinotify.ProcessEvent):
	wm = None
	notifier = None

	def __init__(self, cb):
		self.cb = cb
		pyinotify.ProcessEvent.__init__(self)

	def process_IN_MODIFY(self, event):
		self.cb(event)

	@classmethod
	def init(cls, filename, cb):
		cls.wm = pyinotify.WatchManager()
		cls.notifier = pyinotify.ThreadedNotifier(cls.wm, cls(cb))
		cls.wm.add_watch(filename, pyinotify.IN_MODIFY)
		cls.notifier.start()
		print 'pyinotify is watching', filename

	@classmethod
	def stop(cls):
		cls.notifier.stop()

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
		self.np_status = config['jabber'].has_key('status') and config['jabber']['status']
		self.np_tunes = config['jabber'].has_key('tunes') and config['jabber']['tunes']
		JabberBot.__init__(self, login, password)
		self.log_notifier = None

	def serve_forever(self):
		return JabberBot.serve_forever(self, connect_callback=self.on_connected)

	def on_connected(self):
		self.status_type = self.DND
		LogNotifier.init(self.folder, self.on_inotify)
		self.update_status()

	def on_inotify(self, event):
		try:
			if event.name == 'ardj.short.log':
				return self.update_status()
		except Exception, e:
			print >>sys.stderr, 'Exception in inotify handler:', e
			traceback.print_exc()

	def update_status(self):
		"""
		Updates the status with the current track name.
		Called by inotify, if available.
		"""
		track = self.get_current_track()
		if self.np_status:
			if track.has_key('artist') and track.has_key('title'):
				self.status_message = u'♫ %s — %s' % (track['artist'], track['title'])
			else:
				self.status_message = u'♫ %s' % (track['file'])
		if self.np_tunes:
			self.send_tune(track)

	def get_current(self):
		shortlog = os.path.join(self.folder, 'ardj.short.log')
		if not os.path.exists(shortlog):
			raise Exception('Short log file not found.')
		return open(shortlog, 'r').read().split('\n')[0].split(' ', 2)[2]

	def get_current_track(self):
		result = { 'file': self.get_current(), 'uri': 'http://radio.mirkforce.net/' }
		try:
			tags = get_file_tags(os.path.join(self.folder, result['file']))
			if 'artist' in tags:
				result['artist'] = unicode(tags['artist'][0])
			if 'title' in tags:
				result['title'] = unicode(tags['title'][0])
		except:
			pass
		return result

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
		current = self.get_current()
		return current

	@botcmd
	def delete(self, message, args):
		"delete a file (provided a file name)."
		if not args:
			return 'Usage: delete filename. You can find the name using command "name".'
		if args == 'current':
			args = self.get_current().decode('utf-8')
		filename = os.path.join(self.folder, args.strip())
		if not os.path.exists(filename):
			return 'File "%s" does not exist.' % filename
		os.rename(filename, filename + '.deleted-by-' + message.getFrom().getStripped())
		self.broadcast('%s deleted "%s"' % (message.getFrom().getStripped(), filename))
		return 'File "%s" was removed from the playlist.' % filename

	@botcmd
	def last(self, message, args):
		"show last played files."
		shortlog = os.path.join(self.folder, 'ardj.short.log')
		if not os.path.exists(shortlog):
			raise Exception('Short log file not found.')
		return open(shortlog, 'r').read()

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
			LogNotifier.stop()
			sys.exit(0)
		except Exception, e:
			print >>sys.stderr, 'Error: %s, restarting' % e
			traceback.print_exc()
