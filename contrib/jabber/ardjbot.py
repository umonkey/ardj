#!/usr/bin/env python
# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import re
import sys
import time
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

class ardjbot(JabberBot):
	def __init__(self, config_name):
		self.folder = os.path.dirname(config_name)
		if not os.path.exists(config_name):
			raise Exception('Config file not found: %s' % config_name)
		config = yaml.load(open(config_name, 'r').read())
		self.config = config
		try:
			u, password = config['jabber']['login'].split('@')[0].split(':')
			h = config['jabber']['login'].split('@')[1]
			login = u + '@' + h
			self.users = config['jabber']['access']
		except KeyError:
			raise Exception('Not enough parameters in config.')
		except:
			raise Exception('Incorrect login info, must be user:pass@host.')
		self.np_status = config['jabber'].has_key('status') and config['jabber']['status']
		self.np_tunes = config['jabber'].has_key('tunes') and config['jabber']['tunes']
		JabberBot.__init__(self, login, password)
		self.log_notifier = None
		self.lastfm = LastFmClient(self)

	def serve_forever(self):
		return JabberBot.serve_forever(self, connect_callback=self.on_connected)

	def on_connected(self):
		self.status_type = self.DND
		LogNotifier.init(self.folder, self.on_inotify)
		self.update_status(onstart=True)

	def shutdown(self):
		LogNotifier.stop()
		JabberBot.shutdown(self)

	def on_inotify(self, event):
		try:
			if event.name == 'ardj.short.log':
				return self.update_status()
		except Exception, e:
			print >>sys.stderr, 'Exception in inotify handler:', e
			traceback.print_exc()

	def update_status(self, onstart=False):
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
		if not onstart:
			self.lastfm.submit(track)

	def get_current(self):
		"""Возвращает имя проигрываемого файла из краткого лога."""
		shortlog = os.path.join(self.folder, 'ardj.short.log')
		if not os.path.exists(shortlog):
			raise Exception('Short log file not found.')
		return open(shortlog, 'r').read().split('\n')[0].split(' ', 2)[2]

	def get_current_track(self):
		try:
			result = { 'file': self.get_current(), 'uri': 'http://tmradio.net/' }
			tags = get_file_tags(os.path.join(self.folder, result['file']))
			for tag in ('artist', 'title'):
				if tag in tags:
					result[tag] = unicode(tags[tag][0])
		except Exception, e:
			print 'get_current_track: error=%s' % (e)
			traceback.print_exc()
			result = {}
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
		return 'OK'

	@botcmd
	def last(self, message, args):
		"show last played files."
		shortlog = os.path.join(self.folder, 'ardj.short.log')
		if not os.path.exists(shortlog):
			raise Exception('Short log file not found.')
		return open(shortlog, 'r').read()

	@botcmd
	def move(self, message, args):
		"move a file to a different playlist."
		args = args.split(' ')
		if len(args) < 2:
			return "Usage: move filename|\"current\" playlist_name"
		if args[0] == 'current':
			args[0] = self.get_current().decode('utf-8')
		if args[0].split(os.path.sep)[0] == args[1]:
			return "It's in \"%s\" already." % args[1]
		playlist = args[1]
		if not os.path.exists(os.path.join(self.folder, playlist.encode('utf-8'))):
			available = [d for d in os.listdir(self.folder) if os.path.isdir(os.path.join(self.folder, d))]
			return "Playlist \"%s\" does not exist, available playlists: %s." % (playlist, ', '.join(available))
		src = os.path.join(self.folder, args[0])
		dst = os.path.join(self.folder, playlist, os.path.basename(src))
		if not os.path.exists(src):
			return "File \"%s\" does not exist." % (args[0])
		os.rename(src, dst)
		self.broadcast('%s moved "%s" to playlist "%s".' % (message.getFrom().getStripped(), src.decode('utf-8'), playlist))
		return 'OK'

	@botcmd
	def say(self, message, args):
		"broadcast a message to connected users."
		if len(args):
			self.broadcast('%s said: %s' % (message.getFrom().getStripped(), args), True)

	@botcmd
	def restart(self, message, args):
		"restart the bot"
		self.shutdown()
		sys.exit(1)

class LastFmClient:
	"""
	Last.fm client class. Uses lastfmsubmitd to send track info. Uses config
	file parameter lastfm/skip as a regular expression to match files that
	must never be reported (such as jingles).
	"""
	def __init__(self, bot):
		"""
		Imports and initializes lastfm.client, reads options from bot's config file.
		"""
		self.skip = None
		self.folder = bot.folder
		try:
			import lastfm.client
			self.cli = lastfm.client.Daemon('ardj')
			self.cli.open_log()
		except ImportError:
			print >>sys.stderr, 'Last.fm disabled: please install lastfmsubmitd.'
			self.cli = None
		if bot.config.has_key('lastfm') and bot.config['lastfm'].has_key('skip'):
			self.skip = re.compile(bot.config['lastfm']['skip'])

	def submit(self, track):
		"""
		Reports a track, which must be a dictionary containing keys: file,
		artist, title. If a key is not there, the track is not reported.
		"""
		if self.cli is not None:
			try:
				if self.skip is not None and self.skip.match(track['file']):
					print 'Last.fm: skipped', track['file']
				else:
					filename = os.path.join(self.folder, track['file'])
					self.cli.submit({ 'artist': track['artist'], 'title': track['title'], 'time': time.gmtime(), 'length': mutagen.File(filename).info.length })
			except KeyError, e:
				print >>sys.stderr, 'Last.fm: no %s in %s' % (e.args[0], track)

class LogNotifier(pyinotify.ProcessEvent):
	"""
	Tracks changes in a file using inotify.
	"""
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

	@classmethod
	def stop(cls):
		cls.notifier.stop()

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
			traceback.print_exc()
