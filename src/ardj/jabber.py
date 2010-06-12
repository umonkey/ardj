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
		"""
		Возвращает информацию о последней проигранной дорожке.
		"""
		return self.ardj.get_last_track()

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
		self.broadcast(u'%s set weight=0 for track=%u playlist=%s filename=%s' % (self.get_linked_sender(message), track.id, track.playlist, track.filename))

	@botcmd
	def undelete(self, message, args):
		"undeletes a track (sets weight to 1)"
		track = db.track.load(args or self.get_current_track().id)
		if track.weight == 0:
			track.weight = 1
			track.save()
			self.broadcast(u'%s set weight=1 for track=%u playlist=%s filename=%s' % (self.get_linked_sender(message), track.id, track.playlist, track.filename))
		else:
			return u'Track %u\'s weight is %f, not quite zero.' % (track.id, track.weight)

	@botcmd
	def last(self, message, args):
		"show last 10 played tracks"
		rows = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks ORDER BY last_played DESC LIMIT 10').fetchall()]
		if not rows:
			return u'Nothing was played yet.'
		message = u'Last played tracks:'
		for row in rows:
			message += u'<br/>\n%s — @%s, #%u' % (self.get_linked_title(row), row['playlist'], row['id'])
		return message

	@botcmd
	def show(self, message, args):
		"shows detailed track info"
		args = self.split(args)
		if not args:
			track = self.get_current_track()
		else:
			track = self.ardj.get_track_by_id(int(args[0]))
		if track is None:
			return u'No such track.'
		result = self.get_linked_title(track)
		result += u'; #%u @%s filename="%s" weight=%f playcount=%u length=%us' % (track['id'], track['playlist'], track['filename'], track['weight'], track['count'], track['length'])
		"""
		result += u'. Tags:\n'
		tt = tags.get(track.path)
		for k in tt:
			result += u'%s: %s\n' % (k, tt[k])
		"""
		return result.strip()

	@botcmd
	def say(self, message, args):
		"sends a message to all connected users"
		if len(args):
			self.broadcast(u'%s said: %s' % (self.get_linked_sender(message), args), True)

	@botcmd
	def die(self, message, args):
		"shuts down the bot (should be restarted)"
		self.shutdown()
		sys.exit(1)

	@botcmd
	def select(self, message, args):
		"low level access to the database"
		result = u''
		for row in self.ardj.database.cursor().execute(message.getBody()).fetchall():
			result += u', '.join([unicode(cell) for cell in row]) + u'\n'
		return result

	@botcmd
	def update(self, message, args):
		"low level update to the database"
		sql = 'update ' + args
		if not sql.endswith(';'):
			return u'SQL updates must end with a ; to prevent accidents.'
		self.ardj.database.cursor().execute(sql)
		self.ardj.database.commit()
		self.broadcast(u'SQL from %s: %s' % (self.get_linked_sender(message), sql))

	@botcmd
	def twit(self, message, args):
		"sends a message to twitter"
		if not have_twitter:
			return u'You need to install <a href="http://code.google.com/p/python-twitter/">python-twitter</a> to use this command.'
		username, password = self.ardj.config.get('twitter/name', ''), self.ardj.config.get('twitter/password', '')
		if not username or not password:
			return u'Twitter is not enabled in the config file.'
		try:
			api = twitter.Api(username=username, password=password)
			api.SetXTwitterHeaders(client='ardj', url='http://ardj.googlecode.com/', version='1.0')
		except Exception, e:
			return u'Could not initialize Twitter API: %s' % e
		posting = api.PostUpdate(args)
		url = 'http://twitter.com/' + posting.GetUser().GetScreenName() + '/status/' + str(posting.GetId())
		self.broadcast(u'%s sent <a href="%s">a message</a> to twitter: %s' % (self.get_linked_sender(message), url, args))

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
			self.broadcast(u'%s set %s to %s for track=%u (%s)' % (self.get_linked_sender(mess), prop, value, track.id, track.filename))
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

	def get_linked_title(self, track):
		if not track['artist']:
			return track['filename']
		elif not track['title']:
			link = os.path.basename(track['filename'])
		else:
			link = u'<a href="http://www.last.fm/music/%s/_/%s">%s</a>' % (urllib.quote(track['artist'].encode('utf-8')), urllib.quote(track['title'].encode('utf-8')), track['title'])
		return link + u' by <a href="http://www.last.fm/music/%s">%s</a>' % (urllib.quote(track['artist'].encode('utf-8')), track['artist'])

	def get_linked_sender(self, message):
		name, host = message.getFrom().getStripped().split('@')
		return u'<a href="xmpp:%s@%s">%s</a>' % (name, host, name)

def Open(ardj):
	"""
	Returns a new bot instance.
	"""
	return ardjbot(ardj)

__all__ = ['Open']
