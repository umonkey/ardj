# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import re
import socket # for gethostname()
import sys
import time
import traceback
import urllib

from jabberbot import JabberBot, botcmd
import notify
import tags

def log(msg):
	print >>sys.stderr, msg

try:
	import twitter
	have_twitter = True
except ImportError:
	have_twitter = False

class ardjbot(JabberBot):
	def __init__(self, ardj):
		self.ardj = ardj
		self.twitter = None
		self.filetracker = None

		login, password = self.split_login(self.ardj.config.get('jabber/login'))
		JabberBot.__init__(self, login, password, res=socket.gethostname())

	def get_users(self):
		"""
		Returns the list of authorized jids.
		"""
		return self.ardj.config.get('jabber/access', [])

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
		self.filetracker = notify.monitor([os.path.dirname(self.ardj.config.filename)], self.on_file_changes)

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
		JabberBot.shutdown(self)

	def update_status(self, onstart=False):
		"""
		Updates the status with the current track name.
		Called by inotify, if available.
		"""
		track = self.get_current_track()
		if self.ardj.config.get('jabber/status', False):
			parts = []
			for k in ('artist', 'title'):
				if hasattr(track, k):
					parts.append(getattr(track, k))
			if not parts:
				parts.append(track['file'])
			self.status_message = u'♫ %s' % u' — '.join(parts)
		if self.ardj.config.get('jabber/tunes', True):
			self.send_tune(dict([(k, getattr(track, k)) for k in ('artist', 'title', 'length', 'filename')]))

	def get_current(self):
		"""Возвращает имя проигрываемого файла из краткого лога."""
		return self.get_current_track()['filepath']

	def get_current_track(self):
		return db.track.get_last_tracks(1)[0]

	def check_access(self, message):
		return message.getFrom().split('/')[0] in self.get_users()

	def callback_message(self, conn, mess):
		if mess.getType() == 'chat':
			if mess.getFrom().getStripped() not in self.get_users():
				print >>sys.stderr, mess.getFrom().getStripped(), self.get_users()
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
		rows = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks ORDER BY last_played DESC LIMIT 10').fetchall()]
		if not rows:
			return u'Nothing was played yet.'
		message = u'Last played tracks:<br/>\n'
		for row in rows:
			if row['artist'] and row['title']:
				link = '<a href="http://www.last.fm/music/%s/_/%s">%s</a> by <a href="http://www.last.fm/music/%s">%s</a>' % (urllib.quote(row['artist'].encode('utf-8')), urllib.quote(row['title'].encode('utf-8')), row['title'], urllib.quote(row['artist'].encode('utf-8')), row['artist'])
			else:
				link = row['filename']
			message += u'%s — @%s, #%u<br/>\n' % (link, row['playlist'], row['id'])
		return message

	@botcmd
	def show(self, message, args):
		"shows detailed track info"
		args = self.split(args)
		if not args:
			args.insert(0, self.get_current_track().id)
		track = db.track.load(args[0])
		if track is None:
			return u'No such track.'
		result = u'id=%u playlist=%s filename="%s" artist="%s" title="%s" weight=%f playcount=%u, length=%us' % (track.id, track.playlist, track.filename, track.artist, track.title, track.weight, track.count, track.length)
		result += u'. Tags:\n'
		tt = tags.get(track.path)
		for k in tt:
			result += u'%s: %s\n' % (k, tt[k])
		return result.strip()

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
		self.broadcast('%s sent <a href="%s">a message</a> to twitter: %s' % (message.getFrom().getStripped(), url, args))

	@botcmd
	def echo(self, message, args):
		return args

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

	def run(self):
		while True:
			try:
				self.serve_forever()
				sys.exit(0)
			except Exception, e:
				print >>sys.stderr, 'Error: %s, restarting in 5 seconds.' % e
				traceback.print_exc()
				time.sleep(5)

def Open(ardj):
	"""
	Returns a new bot instance.
	"""
	return ardjbot(ardj)

__all__ = ['Open']
