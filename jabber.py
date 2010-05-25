# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import re
import sys
import traceback

import db
from config import config
from jabberbot import JabberBot, botcmd
import notify
from log import log

have_twitter = False
try:
	import twitter
	have_twitter = True
except ImportError:
	print >>sys.stderr, 'Install python-twitter to get additional features.'

class ardjbot(JabberBot):
	def __init__(self):
		self.config = config()
		self.db = db.db()
		self.users = self.config.get('jabber/access', [])
		self.np_status = self.config.get('jabber/status', True)
		self.np_tunes = self.config.get('jabber/tunes', True)
		self.log_notifier = None
		self.twitter = None
		self.filetracker = None
		self.musicdir_monitor = None
		if have_twitter:
			try:
				self.twitter = twitter.Api(username=self.config.get('twitter/name'), password=self.config.get('twitter/password'))
				self.twitter.SetXTwitterHeaders(client='ardj', url='http://ardj.googlecode.com/', version='1.0')
			except Exception, e:
				log('Twitter: %s' % e)

		login, password = self.split_login(self.config.get('jabber/login'))
		JabberBot.__init__(self, login, password)

	def split_login(self, uri):
		name, password = uri.split('@', 1)[0].split(':', 1)
		host = uri.split('@', 1)[1]
		return (name + '@' + host, password)

	def serve_forever(self):
		"""
		Updates the database, then starts the jabber bot.
		"""
		return JabberBot.serve_forever(self, connect_callback=self.on_connected)

	def on_connected(self):
		self.status_type = self.DND
		self.filetracker = notify.monitor([os.path.dirname(self.config.filename)], self.on_file_changes)
		self.musicdir_monitor = db.track.monitor()

	def on_file_changes(self, action, path):
		try:
			if path == self.db.filename:
				if 'modified' == action:
					return self.update_status()
		except Exception, e:
			log('Exception in inotify handler: %s' % e)
			traceback.print_exc()

	def shutdown(self):
		self.filetracker.stop()
		if self.musicdir_monitor is not None:
			self.musicdir_monitor.stop()
		JabberBot.shutdown(self)

	def update_status(self, onstart=False):
		"""
		Updates the status with the current track name.
		Called by inotify, if available.
		"""
		track = self.get_current_track()
		if self.np_status:
			parts = []
			for k in ('artist', 'title'):
				if hasattr(track, k):
					parts.append(getattr(track, k))
			if not parts:
				parts.append(track['file'])
			self.status_message = u'♫ %s' % u' — '.join(parts)
		if self.np_tunes:
			self.send_tune(dict([(k, getattr(track, k)) for k in ('artist', 'title', 'length', 'filename')]))

	def get_current(self):
		"""Возвращает имя проигрываемого файла из краткого лога."""
		return self.get_current_track()['filepath']

	def get_current_track(self):
		return db.track.get_last_tracks(1)[0]

	def check_access(self, message):
		return message.getFrom().split('/')[0] in self.users

	def callback_message(self, conn, mess):
		if mess.getType() == 'chat':
			if mess.getFrom().getStripped() not in self.users:
				return self.send_simple_reply(mess, 'No access for you.')
		return JabberBot.callback_message(self, conn, mess)

	@botcmd
	def delete(self, message, args):
		"deletes a track (sets weight to 0)"
		track = db.track.load(args or self.get_current_track().id)
		if track.weight == 0:
			return u'Zero weight already.'
		elif track.weight > 1:
			return u'This track is protected (weight=%f), use \'set weight to 0\' if you are sure.' % track.weight
		track.weight = 0
		track.save()
		self.broadcast('%s set weight=0 for track=%u playlist=%s filename=%s' % (message.getFrom().getStripped(), track.id, track.playlist, track.filename))

	@botcmd
	def undelete(self, message, args):
		"undeletes a track (sets weight to 1)"
		track = db.track.load(args or self.get_current_track().id)
		if track.weight == 0:
			track.weight = 1
			track.save()
			self.broadcast('%s set weight=1 for track=%u playlist=%s filename=%s' % (message.getFrom().getStripped(), track.id, track.playlist, track.filename))
		else:
			return u'Track %u\'s weight is %f, not quite zero.' % (track.id, track.weight)

	@botcmd
	def last(self, message, args):
		"show last 10 played tracks"
		tracks = db.track.get_last_tracks()
		if not tracks:
			return u'Nothing was played yet.'
		return u'Last played tracks:\n' + u'\n'.join(['%5u. %s (playlist=%s, weight=%f)' % (t.id, t.filename, t.playlist, t.weight) for t in tracks])

	@botcmd
	def show(self, message, args):
		"shows detailed track info"
		args = self.split(args)
		if not args:
			args.insert(0, self.get_current_track().id)
		track = db.track.load(args[0])
		if track is None:
			return u'No such track.'
		return u'id=%u playlist=%s filename="%s" artist="%s" title="%s" weight=%f playcount=%u, length=%us' % (track.id, track.playlist, track.filename, track.artist, track.title, track.weight, track.count, track.length)

	@botcmd
	def say(self, message, args):
		"sends a message to all connected users"
		if len(args):
			self.broadcast('%s said: %s' % (message.getFrom().getStripped(), args), True)

	@botcmd
	def die(self, message, args):
		"shuts down the bot (should be restarted)"
		self.shutdown()
		sys.exit(1)

	@botcmd
	def select(self, message, args):
		"low level access to the database"
		result = u''
		for row in self.db.cursor().execute(message.getBody()).fetchall():
			result += u', '.join([unicode(cell) for cell in row]) + u'\n'
		return result

	@botcmd
	def update(self, message, args):
		"low level update to the database"
		sql = 'update ' + args
		if not sql.endswith(';'):
			return u'SQL updates must end with a ; to prevent accidents.'
		self.db.cursor().execute(sql)
		self.db.commit()
		self.broadcast('SQL from %s: %s' % (message.getFrom().getStripped(), sql))

	@botcmd
	def twit(self, message, args):
		"sends a message to twitter"
		if not have_twitter:
			return 'You need to install python-twitter to use this command.'
		posting = self.twitter.PostUpdate(args)
		url = 'http://twitter.com/' + posting.GetUser().GetScreenName() + '/status/' + str(posting.GetId())
		self.broadcast('%s sent a message to twitter: %s <%s>' % (message.getFrom().getStripped(), args, url))

	def unknown_command(self, mess, cmd, args):
		m = re.match('(?:for (\w+) )?set (\w+) to (.*)$', cmd + ' ' + args)
		if m is not None:
			id, prop, value = m.groups()
			usage = u'Usage: "[for id] set prop to value", where prop is artist, playlist, title or weight.'
			if prop not in ('artist', 'playlist', 'title', 'weight'):
				return usage
			# Load the track:
			if id is None: track = self.get_current_track()
			else: track = db.track.load(id)
			# Update the value:
			if 'weight' == prop:
				if track.weight == float(value):
					return u'OK already.'
				track.weight = float(value)
			elif prop in ('artist', 'playlist', 'title'): setattr(track, prop, value)
			else: return usage
			# Get over it:
			track.save()
			self.broadcast('%s set %s to %s for track=%u (%s)' % (mess.getFrom().getStripped(), prop, value, track.id, track.filename))
			return None
		return JabberBot.unknown_command(self, mess, cmd, args)

	def split(self, args):
		if not args:
			return []
		return args.split(u' ')

def run():
	try:
		bot = ardjbot()
	except Exception, e:
		log(e)
		traceback.print_exc()
		sys.exit(1)

	while True:
		try:
			bot.serve_forever()
			sys.exit(0)
		except Exception, e:
			log('Error: %s, restarting' % e)
			traceback.print_exc()
