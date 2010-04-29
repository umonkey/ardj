# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import sys
import traceback

import db
from config import config
from jabberbot import JabberBot, botcmd
from notify import LogNotifier

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
		if have_twitter:
			try:
				self.twitter = twitter.Api(username=self.config.get('twitter/name'), password=self.config.get('twitter/password'))
				self.twitter.SetXTwitterHeaders(client='ardj', url='http://ardj.googlecode.com/', version='1.0')
			except Exception, e:
				print >>sys.stderr, 'Twitter: %s' % e

		login, password = self.split_login(self.config.get('jabber/login'))
		JabberBot.__init__(self, login, password)

	def split_login(self, uri):
		name, password = uri.split('@', 1)[0].split(':', 1)
		host = uri.split('@', 1)[1]
		return (name + '@' + host, password)

	def serve_forever(self):
		return JabberBot.serve_forever(self, connect_callback=self.on_connected)

	def on_connected(self):
		self.status_type = self.DND
		# LogNotifier.init(self.config.folder, self.on_inotify)
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

	def get_current(self):
		"""Возвращает имя проигрываемого файла из краткого лога."""
		return self.get_current_track()['filepath']

	def get_current_track(self):
		return self.db.get_last_tracks(1)[0]

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
		track = self.db.get_track_info(args or self.get_current_track()['id'])
		self.db.set_track_weight(track['id'], 0)
		self.broadcast('%s set weight=0 for track=%u (%s/%s)' % (message.getFrom().getStripped(), track['id'], track['playlist'], track['filename']))

	@botcmd
	def undelete(self, message, args):
		"undeletes a track (sets weight to 1)"
		track = self.db.get_track_info(args or self.get_current_track()['id'])
		self.db.set_track_weight(track['id'], 1.0)
		self.broadcast('%s set weight=1 for track=%u (%s/%s)' % (message.getFrom().getStripped(), track['id'], track['playlist'], track['filename']))

	@botcmd
	def last(self, message, args):
		"show last 10 played tracks"
		return u'\n'.join(['%s/%s (id=%u, weight=%f)' % (t['playlist'], t['name'], t['id'], t['weight']) for t in self.db.get_last_tracks()])

	@botcmd
	def show(self, message, args):
		"shows detailed track info"
		args = self.split(args)
		if not args:
			args.insert(0, self.get_current_track()['id'])
		track = self.db.get_track_info(args[0])
		if track is None:
			return u'No such track.'
		return u'id=%u playlist=%s filename="%s" artist="%s" title="%s" weight=%f playcount=%u queue=%f' % (track['id'], track['playlist'], track['filename'], track['artist'], track['title'], track['weight'], track['count'], track['queue'])

	@botcmd
	def move(self, message, args):
		"moves a track to a different playlist"
		args = self.split(args)
		if len(args) < 3:
			args.insert(0, self.get_current_track()['id'])
		if len(args) != 3 or args[1] != 'to':
			return 'Usage: move [id] to <playlist>'
		self.db.move_track_to(args[0], args[2])
		self.broadcast('%s moved track %u to playlist "%s".' % (message.getFrom().getStripped(), args[0], args[2]))

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
	def twit(self, message, args):
		"sends a message to twitter"
		if not have_twitter:
			return 'You need to install python-twitter to use this command.'
		posting = self.twitter.PostUpdate(args)
		url = 'http://twitter.com/' + posting.GetUser().GetScreenName() + '/status/' + str(posting.GetId())
		self.broadcast('%s sent a message to twitter: %s <%s>' % (message.getFrom().getStripped(), args, url))

	def split(self, args):
		if not args:
			return []
		return args.split(u' ')

def run():
	try:
		bot = ardjbot()
	except Exception, e:
		print >>sys.stderr, e
		traceback.print_exc()
		sys.exit(1)

	while True:
		try:
			bot.serve_forever()
			sys.exit(0)
		except Exception, e:
			print >>sys.stderr, 'Error: %s, restarting' % e
			traceback.print_exc()
