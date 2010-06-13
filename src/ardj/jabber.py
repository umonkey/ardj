# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import re
import socket # for gethostname()
import subprocess
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
		self.dbtracker = None

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
		self.dbtracker = notify.monitor([self.ardj.database.filename], self.on_file_changes)

	def on_file_changes(self, action, path):
		try:
			if path == self.ardj.database.filename:
				if 'modified' == action:
					return self.update_status()
		except Exception, e:
			log('Exception in inotify handler: %s' % e)
			traceback.print_exc()

	def shutdown(self):
		self.dbtracker.stop()
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
				if track.has_key(k):
					parts.append(track[k])
			if not parts:
				parts.append(track['filename'])
			self.status_message = u'♫ %s' % u' — '.join(parts)
		if self.ardj.config.get('jabber/tunes', True):
			self.send_tune(track)

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
	def set(self, message, args):
		"modify track properties"
		r = re.match('(\S+)\s+to\s+(.+)\s+for\s+(\d+)$', args)
		if r:
			a1, a2, a3 = r.groups()
			track = self.ardj.get_track_by_id(int(a3))
		else:
			r = re.match('(\S+)\s+to\s+(.+)$', args)
			if r:
				a1, a2 = r.groups()
				track = self.get_current_track()
			else:
				return u'Syntax: set prop to value [for id]'

		types = { 'playlist': unicode, 'artist': unicode, 'title': unicode, 'weight': float }
		if a1 not in types:
			return u'Unknown property: %s, available: %s.' % (a1, u', '.join(types.keys()))

		try:
			a2 = types[a1](a2)
		except Exception, e:
			return u'Wrong data type for property %s: %s' % (a1, e)

		old = track[a1]
		if old == a2:
			return u'That\'s the current value, yes.'

		track[a1] = a2
		self.ardj.update_track(track)

		self.broadcast(u'%s changed %s from "%s" to "%s" for %s; #%u @%s' % (self.get_linked_sender(message), a1, old, a2, self.get_linked_title(track), track['id'], track['playlist']))

	@botcmd
	def delete(self, message, args):
		"delete a track (sets weight to 0)"
		track = args and self.ardj.get_track_by_id(int(args)) or self.get_current_track()
		if not track['weight']:
			return u'Zero weight already.'
		elif track['weight'] > 1:
			return u'This track is protected (weight=%f), use \'set weight to 0\' if you are sure.' % track['weight']
		old = track['weight']
		track['weight'] = 0
		self.ardj.update_track(track)
		self.broadcast(u'%s changed weight from %s to 0 for %s; #%u @%s' % (self.get_linked_sender(message), old, self.get_linked_title(track), track['id'], track['playlist']))
		self.skip(message, args)

	@botcmd
	def undelete(self, message, args):
		"undelete a track (sets weight to 1)"
		track = args and self.ardj.get_track_by_id(int(args)) or self.get_current_track()
		if track['weight']:
			return u'This track\'s weight is %s, not quite zero.' % (track['weight'])
		track['weight'] = 1.
		self.ardj.update_track(track)
		self.broadcast(u'%s changed weight from 0 to 1 for %s; #%u @%s' % (self.get_linked_sender(message), self.get_linked_title(track), track['id'], track['playlist']))

	@botcmd
	def skip(self, message, args):
		"skip to next track"
		try:
			self.send_signal('USR1', 'ices')
			return u'ok'
		except Exception, e:
			return unicode(e)

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
		"show detailed track info"
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
		"send a message to all connected users"
		if len(args):
			self.broadcast(u'%s said: %s' % (self.get_linked_sender(message), args), True)

	@botcmd
	def die(self, message, args):
		"shut down the bot (should be restarted)"
		self.shutdown()
		sys.exit(1)

	@botcmd
	def select(self, message, args):
		"low level access to the database"
		result = u''
		for row in self.ardj.database.cursor().execute(message.getBody()).fetchall():
			result += u', '.join([unicode(cell) for cell in row]) + u'\n'
		if not result:
			result = u'Nothing.'
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
		"send a message to twitter"
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
		"send back the arguments"
		return args

	def split(self, args):
		if not args:
			return []
		return args.split(u' ')

	def run(self):
		while True:
			try:
				self.serve_forever()
				return
			except Exception, e:
				print >>sys.stderr, 'Error: %s, restarting in 5 seconds.' % e
				traceback.print_exc()
				time.sleep(5)

	@botcmd
	def purge(self, message, args):
		"erase tracks with zero weight"
		cur = self.ardj.database.cursor()
		musicdir = self.ardj.config.get_music_dir()
		for id, filename in [(row[0], os.path.join(musicdir, row[1].encode('utf-8'))) for row in cur.execute('SELECT id, filename FROM tracks WHERE weight = 0').fetchall()]:
			if os.path.exists(filename):
				os.unlink(filename)
		cur.execute('DELETE FROM tracks WHERE weight = 0')
		self.ardj.database.commit()
		return u'OK'

	@botcmd
	def sync(self, message, args):
		"update database (finds new and dead files)"
		return self.ardj.sync()

	def get_linked_title(self, track):
		if not track['artist']:
			return track['filename']
		elif not track['title']:
			link = os.path.basename(track['filename'])
		else:
			link = u'<a href="http://www.last.fm/music/%s/_/%s">%s</a>' % (urllib.quote(track['artist'].encode('utf-8')), urllib.quote(track['title'].encode('utf-8')), track['title'])
		return link + u' by <a href="http://www.last.fm/music/%s">%s</a>' % (urllib.quote(track['artist'].encode('utf-8')), track['artist'])

	@botcmd
	def reload(self, message, args):
		"reload ices config and playlist scripts"
		try:
			self.send_signal('HUP', 'ices')
			return u'ok'
		except Exception, e:
			return unicode(e)

	def get_linked_sender(self, message):
		name, host = message.getFrom().getStripped().split('@')
		return u'<a href="xmpp:%s@%s">%s</a>' % (name, host, name)

	def send_signal(self, sig, prog):
		"""
		Sends a signal to the specified program. Returns True on success.
		"""
		cmd = '/usr/bin/killall'
		if not os.path.exists(cmd):
			raise Exception(u'%s is not available.' % cmd)
		if subprocess.Popen([cmd, '-' + sig, prog]).wait():
			raise Exception(u'Could not skip. Is '+ prog +' running?')
		return True

def Open(ardj):
	"""
	Returns a new bot instance.
	"""
	return ardjbot(ardj)

__all__ = ['Open']
