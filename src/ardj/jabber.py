# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import math
import os
import re
import shutil # move()
import socket # for gethostname()
import subprocess
import sys
import time
import traceback
import urllib
from xml.sax import saxutils

from ardj.jabberbot import JabberBot, botcmd
from ardj.filebot import FileBot, FileNotAcceptable
import notify
import tags

def log(msg):
	print >>sys.stderr, msg

try:
	import twitter
	have_twitter = True
except ImportError:
	have_twitter = False

class MyFileReceivingBot(FileBot):
	def is_file_acceptable(self, sender, filename, filesize):
		if not self.check_access(sender):
			self.log('Refusing to accept files from %s.' % sender)
			raise FileNotAcceptable('I\'m not allowed to receive files from you, sorry.')
		if os.path.splitext(filename.lower())[1] not in ['.mp3', '.ogg']:
			raise FileNotAcceptable('I only accept MP3 and OGG files, which "%s" doesn\'t look like.' % os.path.basename(filename))

	def callback_file(self, sender, filename):
		dst_path = os.path.join(self.ardj.config.get_music_dir(), 'incoming', sender.split('/')[0])
		if not os.path.exists(dst_path):
			os.makedirs(dst_path)

		dst_name = self.add_filename_suffix(os.path.join(dst_path, os.path.basename(filename)))
		shutil.move(filename, dst_name)

		self.log('Received %s.' % dst_name)
		track_id = self.ardj.add_track_from_file(dst_name)

		return 'Your file was assigned number %u. Use the "news" command to see last added files, "set playlist to xyz for %u" to move this file from @incoming.' % (track_id, track_id)

	def add_filename_suffix(self, filename):
		"""
		Makes sure that filename does not exist by addind a numeric index
		to the file's name if necessary.
		"""
		source = filename
		index = 1
		while os.path.exists(filename):
			parts = os.path.splitext(source)
			filename = parts[0] + '_' + unicode(index) + parts[1]
			index += 1
		return filename

class ardjbot(MyFileReceivingBot):
	def __init__(self, ardj):
		self.ardj = ardj
		self.twitter = None
		self.dbtracker = None
		self.pidfile = '/tmp/ardj-jabber.pid'
		self.publicCommands = self.ardj.config.get('jabber/public-commands', 'help rocks sucks show last hitlist shitlist').split(' ')

		login, password = self.split_login(self.ardj.config.get('jabber/login'))
		super(ardjbot, self).__init__(login, password, res=socket.gethostname(), debug=ardj.debug)

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
		# self.status_type = self.DND
		self.dbtracker = notify.monitor([self.ardj.database.filename], self.on_file_changes)
		if self.pidfile:
			try:
				open(self.pidfile, 'w').write(str(os.getpid()))
			except IOError, e:
				print >>sys.stderr, 'Could not write to %s: %s' % (self.pidfile, e)
		self.update_status()

	def on_file_changes(self, action, path):
		try:
			if path == self.ardj.database.filename:
				if 'modified' == action:
					return self.update_status()
		except IOError, e:
			log('IOError: %s, shutting down.' % e)
			self.quit()
		except Exception, e:
			log('Exception in inotify handler: %s' % e)
			traceback.print_exc()

	def shutdown(self):
		self.on_disconnect()
		JabberBot.shutdown(self)
		if self.pidfile and os.path.exists(self.pidfile):
			os.unlink(self.pidfile)

	def update_status(self, onstart=False):
		"""
		Updates the status with the current track name.
		Called by inotify, if available.
		"""
		track = self.get_current_track()
		if track is not None:
			if self.ardj.config.get('jabber/status', False):
				if track.has_key('artist') and track.has_key('title'):
					status = u'«%s» by %s' % (track['title'], track['artist'])
				else:
					status = os.path.basename(track['filename'])
				status += u' — #%u @%s ♺%u' % (track['id'], track['playlist'], track['count'])
				self.status_message = status
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

	def check_access(self, sender):
		return sender.split('/')[0] in self.get_users()

	def callback_message(self, conn, mess):
		if mess.getType() == 'chat':
			is_public = mess.getBody().strip().split(' ')[0] in self.publicCommands
			if not is_public and not self.check_access(mess.getFrom().getStripped()):
				self.log('Refusing access to %s.' % mess.getFrom())
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

		types = { 'playlist': unicode, 'artist': unicode, 'title': unicode }
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
		"delete a track (sets weight to 0)\n\nUsage: delete track_id\n  or:\nUsage: delete from table where ...;"
		if args.lower().startswith('from'):
			if not args.endswith(';'):
				return u'SQL commands must end with a ; to prevent accidents.'
			self.ardj.database.cursor().execute(u'delete ' + args)
			self.ardj.database.commit()
			return u'ok'
		track = args and self.ardj.get_track_by_id(int(args)) or self.get_current_track()
		if not track['weight']:
			return u'Zero weight already.'
		elif track['weight'] > 1:
			return u'This track is protected (weight=%f), use \'set weight to 0\' if you are sure.' % track['weight']
		old = track['weight']
		track['weight'] = 0
		self.ardj.update_track(track)
		self.broadcast(u'%s changed weight from %s to 0 for %s; #%u @%s' % (self.get_linked_sender(message), old, self.get_linked_title(track), track['id'], track['playlist']))
		if not args:
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
			if track is None:
				return 'Nothing is playing.'
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
		self.quit(1)

	@botcmd
	def select(self, message, args):
		"low level access to the database"
		result = u''
		for row in self.ardj.database.cursor().execute(message.getBody()).fetchall():
			result += u', '.join([unicode(cell) for cell in row]) + u'\n<br/>'
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
		try:
			return self.serve_forever()
		except Exception, e:
			print >>sys.stderr, 'Error: %s.' % e
			traceback.print_exc()
			return 1

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
		return u'ok'

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
			link = u'«<a href="http://www.last.fm/music/%s/_/%s">%s</a>»' % (urllib.quote(track['artist'].strip().encode('utf-8')), urllib.quote(track['title'].strip().encode('utf-8')), saxutils.escape(track['title'].strip()))
		link += u' by <a href="http://www.last.fm/music/%s">%s</a>' % (urllib.quote(track['artist'].strip().encode('utf-8')), saxutils.escape(track['artist'].strip()))
		return link

	@botcmd
	def reload(self, message, args):
		"reload ices config and playlist scripts"
		try:
			self.send_signal('HUP', 'ices')
			return u'Ices will be reinitialized when the track changes.'
		except Exception, e:
			return unicode(e)

	@botcmd
	def rocks(self, message, args):
		"express your love for the current track"
		track = self.get_current_track()
		if track is None:
			return 'Nothing is playing.'
		else:
			return self.__vote(track['id'], message.getFrom().getStripped(), 1)

	@botcmd
	def sucks(self, message, args):
		"express your hate for the current track"
		track = self.get_current_track()
		if track is None:
			return 'Nothing is playing.'
		else:
			return self.__vote(track['id'], message.getFrom().getStripped(), -1)

	@botcmd
	def shitlist(self, message, args):
		"list tracks with zero weight"
		tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks WHERE weight = 0 ORDER BY title, artist').fetchall()]
		if not tracks:
			return u'The shitlist is empty.'
		message = u'The shitlist has %u items:' % len(tracks)
		for track in tracks:
			message += u'\n<br/>%s — #%u @%s' % (self.get_linked_title(track), track['id'], track['playlist'])
		message += u'\n<br/>Use the "purge" command to erase these tracks.'
		return message

	@botcmd
	def hitlist(self, message, args):
		"shows X top rated tracks"
		limit = args and int(args) or 10
		tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4], 'weight': row[5] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist, weight FROM tracks WHERE weight > 0 ORDER BY weight DESC LIMIT ' + str(limit)).fetchall()]
		if not tracks:
			return u'The hitlist is empty.'
		message = u'Top %u tracks:' % len(tracks)
		for track in tracks:
			message += u'\n<br/>  %s — #%u @%s %%%s' % (self.get_linked_title(track), track['id'], track['playlist'], track['weight'])
		return message

	@botcmd
	def queue(self, message, args):
		u"adds a track to queue\n\nUsage: queue [track_id...]"
		cur = self.ardj.database.cursor()
		if args:
			ids = [int(x) for x in args.split(' ') if x]
			for id in ids:
				self.ardj.queue_track(id, cur)
			self.ardj.database.commit()
		tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4], 'qid': row[5] } for row in self.ardj.database.cursor().execute('SELECT t.id, t.filename, t.artist, t.title, t.playlist, q.id FROM tracks t INNER JOIN queue q ON q.track_id = t.id ORDER BY q.id').fetchall()]
		if not tracks:
			return u'Queue empty, use "queue track_id..." to fill.'
		message = u'Current queue:'
		for track in tracks:
			message += u'\n<br/>%u. %s — #%u @%s' % (track['qid'], self.get_linked_title(track), track['id'], track['playlist'])
		return message + u'\n<br/>Use "queue track_id..." to add more tracks and "find xyz" to find some ids.'

	@botcmd
	def find(self, mess, args):
		u"finds a track\n\nUsage: find substring\nLists all tracks that contain this substring in the artist, track or file name. The substring can contain spaces. If you want to see more than 10 matching tracks, use the select command, e.g.: SELECT id, filename FROM tracks WHERE ..."
		if not args:
			return self.find.__doc__.split('\n\n')[1]
		like = '%' + args + '%'
		tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks WHERE artist LIKE ? OR title LIKE ? OR filename LIKE ? ORDER BY id LIMIT 10', (like, like, like, )).fetchall()]
		if not tracks:
			return u'No matching tracks.'
		message = u'Found %u tracks:' % len(tracks)
		for track in tracks:
			message += u'\n<br/>  %s — #%u @%s' % (self.get_linked_title(track), track['id'], track['playlist'])
		return message + u'\n<br/>You might want to use "queue track_ids..." now.'

	@botcmd
	def news(self, mess, args):
		u"shows last added tracks"
		tracks = [{ 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'playlist': row[4] } for row in self.ardj.database.cursor().execute('SELECT id, filename, artist, title, playlist FROM tracks ORDER BY id DESC LIMIT 10').fetchall()]
		if not tracks:
			return u'No news.'
		message = u'Last %u tracks:' % len(tracks)
		for track in tracks:
			message += u'\n<br/>  %s — #%u @%s' % (self.get_linked_title(track), track['id'], track['playlist'])
		return message

	def send_simple_reply(self, mess, text, private=False):
		"""
		Splits long messages and sends them in parts.
		"""
		linelimit = 30
		delay = 2

		lines = text.split(u'\n')
		parent = super(ardjbot, self)
		if len(lines) <= linelimit:
			return parent.send_simple_reply(mess, text, private)

		current = 1
		total = math.ceil(float(len(lines)) / float(linelimit))
		parent.send_simple_reply(mess, u'The response it too long (%u lines), sending in %u messages, up to %u lines each, with a %u seconds delay.' % (len(lines), total, linelimit, delay), private)
		while len(lines) and not parent.is_shutting_down():
			prefix = u'[part %u of %u]\n<br/>' % (current, total)
			parent.send_simple_reply(mess, prefix + u'\n'.join(lines[:linelimit]), private)
			del lines[:linelimit]
			current += 1
			time.sleep(delay)

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

	def connect(self):
		"""
		Extends the parent method by registering a disconnect handler.
		"""
		conn = super(ardjbot, self).connect()
		conn.RegisterDisconnectHandler(self.on_disconnect)
		return conn

	def on_disconnect(self):
		if self.dbtracker:
			self.log('on_disconnect: stopping dbtracker.')
			self.dbtracker.stop()
			self.dbtracker = None

	def __vote(self, track_id, email, vote):
		cur = self.ardj.database.cursor()
		# store the vote
		cur.execute('DELETE FROM votes WHERE track_id = ? AND email = ?', (track_id, email, ))
		cur.execute('INSERT INTO votes (track_id, email, vote) VALUES (?, ?, ?)', (track_id, email, vote, ))
		# update track weight
		votes = cur.execute('SELECT SUM(vote) FROM votes WHERE track_id = ?', (track_id, )).fetchall()[0][0]
		cur.execute('UPDATE tracks SET weight = ? WHERE id = ?', (1 + votes * 0.5, track_id, ))
		self.ardj.database.commit()
		return u'OK'

def Open(ardj):
	"""
	Returns a new bot instance.
	"""
	return ardjbot(ardj)

__all__ = ['Open']
