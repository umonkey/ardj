# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import hashlib
import os
import random
import scrobbler
import sys
import time
import traceback

import tags

try:
	from sqlite3 import dbapi2 as sqlite
	from sqlite3 import OperationalError
except ImportError:
	print >>sys.stderr, 'Please install pysqlite2.'
	sys.exit(13)

import config
from log import log
import tags
			
class db:
	# Database connection
	instance = None

	"""
	Interface to the database.
	"""
	def __init__(self):
		"""
		Opens the database, creates tables if necessary.
		"""
		self.config = config.config()
		self.filename = self.config.get_db_name()
		self.folder = os.path.dirname(self.filename)
		self.musicdir = self.config.get_music_dir()
		isnew = not os.path.exists(self.filename)
		self.db = sqlite.connect(self.filename, check_same_thread=False)
		self.db.create_function('randomize', 4, self.sqlite_randomize)
		if isnew:
			log('db: initializing the database')
			cur = self.db.cursor()
			cur.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT, last_played INTEGER)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_playlists_last ON playlists (last_played)')
			cur.execute('CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, playlist TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, artist_weight REAL, weight REAL, count INTEGER, last_played INTEGER, queue INTEGER)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON tracks (playlist)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_queue ON tracks (queue)')
		self.scrobbler = scrobbler.client()

	def sqlite_randomize(self, id, artist_weight, weight, count):
		"""
		The randomize() function for SQLite.
		"""
		result = weight

		# применяем коэффициент исполнителя (= 1 / количество_дорожек)
		result = result * artist_weight

		# делим на количество проигрываний, чтобы стимулировать
		# дорожки, которые проигрываются реже
		result = result / (count + 1)

		# log('randomize(%05u, %f, %f, %u) = %f' % (id, artist_weight, weight, count, result))
		return result

	def cursor(self):
		"""
		Returns a new SQLite cursor, for internal use.
		"""
		return self.db.cursor()

	def commit(self):
		"""
		Commits current transaction, for internal use.
		"""
		self.db.commit()

	def rollback(self):
		"""
		Cancel pending changes.
		"""
		self.db.rollback()

	def get_playlist_stats(self):
		"""
		Returns last played times for playlists, in the form of a dictionary.
		"""
		res = {}
		cur = self.cursor().execute('SELECT name, last_played FROM playlists')
		for row in cur.fetchall() or []:
			res[row[0]] = row[1] or 0
		return res

	def get_random_track(self, scrobble=False):
		skip_artists = self.get_last_artists()
		for playlist in self.get_playlists():
			repeat = None
			if playlist.has_key('repeat'):
				repeat = playlist['repeat']
			track = self.get_random_track_from_playlist(playlist['name'], repeat, skip_artists)
			if track is not None:
				if scrobble:
					self.scrobbler.submit(track)
				return track

	def get_last_artists(self):
		"""
		Returns names of 5 last played artists.
		"""
		dupes = self.config.get('dupes', 0)
		if not dupes:
			return []
		return [row[0] for row in self.cursor().execute('SELECT artist FROM tracks WHERE artist is not null ORDER BY last_played DESC LIMIT ' + str(dupes)).fetchall()]

	def get_playlists(self):
		"""
		Returns all unblocked playlists.
		"""
		def in_list(value, lst):
			if type(lst) != type([]):
				lst = list(lst)
			return value in lst

		stats = self.get_playlist_stats()
		musicdir = self.config.get_music_dir()
		playlists = []
		for playlist in self.config.get('playlists', []):
			if playlist.has_key('name'):
				dir = os.path.join(musicdir, playlist['name'])
				if not stats.has_key(playlist['name']):
					pass
				elif not os.path.exists(dir):
					log('Playlist %s folder does not exist.' % playlist['name'])
				elif not os.path.isdir(dir):
					log('Playlist %s does not point to a folder.' % playlist['name'])
				elif playlist.has_key('delay') and (playlist['delay'] * 60) + stats[playlist['name']] > int(time.time()):
					pass # log('Playlist %s is delayed.' % playlist['name'])
				elif playlist.has_key('hours') and not in_list(int(time.strftime('%H')), playlist['hours']):
					pass # log('Playlist %s is not active on this hour.' % playlist['name'])
				elif playlist.has_key('days') and not in_list(self.get_current_day_number(), playlist['days']):
					pass # log('Playlist %s is not active on this day.' % playlist['name'])
				else:
					playlists.append(playlist)
		return playlists

	def get_current_day_number(self):
		return int(time.strftime('%w')) or 7

	def get_random_track_id(self, playlist, repeat=None, skip_artists=None):
		"""
		Returns id of a random track.
		"""
		sql = 'SELECT id, randomize(id, artist_weight, weight, count) AS w, count FROM tracks WHERE playlist = ? AND w > 0'
		params = (playlist, )
		if repeat is not None:
			sql += ' AND count < ?'
			params += (repeat, )
		if skip_artists is not None:
			tsql = []
			for name in skip_artists:
				tsql.apend('?')
				params += (name, )
			sql += ' AND artist NOT IN (%)' % ', '.join(tsql)
		rows = self.cursor().execute(sql, params).fetchall()
		if not rows:
			return None
		probability_sum = sum([row[1] for row in rows])
		init_rnd = rnd = random.random() * probability_sum
		for row in rows:
			if rnd < row[1]:
				log('db: track %u(%s) won with p=%.4f s=%.4f r=%.4f c=%u' % (row[0], playlist, row[1], probability_sum, init_rnd, row[2]))
				return row[0]
			rnd = rnd - row[1]
		raise Exception(u'This can not happen (could not choose from %u tracks).' % len(rows))

	def get_random_track_from_playlist(self, playlist, repeat=None, skip_artists=None, retry=5):
		"""
		Returns information about a random track from the specified playlist,
		in the form of a dictionary with keys: file, path, title, artist.

		If repeat is given, only tracks with less plays are looked at.

		If there are no files, returns None. Files that do not exist are
		deleted from the database.
		"""
		id = self.get_random_track_id(playlist, repeat)
		if id is None:
			return None
		track = self.get_track_info(id)
		if track is not None:
			if skip_artists is not None and track['artist'] in skip_artists:
				if 1 == retry:
					return None
				return self.get_random_track_from_playlist(playlist, repeat, skip_artists, retry - 1)
			if not os.path.exists(track['filepath']):
				self.cursor().execute('DELETE FROM tracks WHERE id = ?', (track['id'], ))
				log('db: deleted %s/%s' % (track['playlist'], track['filename']))
				self.commit()
				if 1 == retry:
					return None
				return self.get_random_track_from_playlist(playlist, repeat, skip_artists, retry - 1)
			now = int(time.time())
			self.cursor().execute('UPDATE tracks SET count = ?, last_played = ?, queue = 0 WHERE id = ?', (track['count'] + 1, now, track['id'], ))
			self.cursor().execute('UPDATE playlists SET last_played = ? WHERE name = ?', (now, playlist, ))
			return track

	def get_last_tracks(self, limit=10):
		"""
		Returns information about few last played tracks.
		"""
		return [{ 'playlist': row[0], 'name': row[1], 'artist': row[2], 'title': row[3], 'id': row[4], 'weight': row[5] } for row in self.cursor().execute('SELECT playlist, name, artist, title, id, weight FROM tracks ORDER BY last_played DESC LIMIT ' + str(limit)).fetchall()]

	def get_track_info(self, id):
		"""
		Returns information about a particular track.
		"""
		row = self.cursor().execute('SELECT playlist, name, artist, title, id, weight, count, queue, length, artist_weight FROM tracks WHERE id = ?', (int(id), )).fetchone()
		return { 'playlist': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'filepath': os.path.join(self.config.get_music_dir(), row[0], row[1]), 'uri': 'http://tmradio.net/', 'id': row[4], 'weight': row[5], 'count': row[6], 'queue': row[7], 'length': row[8], 'artist_weight': row[9] }

	def get_stats(self):
		count, length = 0, 0
		for row in self.cursor().execute('SELECT length FROM tracks WHERE weight > 0').fetchall():
			count = count + 1
			length = length + row[0]
		return (count, length)

	def set_track_weight(self, track_id, weight):
		self.cursor().execute('UPDATE tracks SET weight = ? WHERE id = ?', (float(weight), int(track_id), ))
		self.commit()

	def set_track_queue(self, track_id, queue):
		self.cursor().execute('UPDATE tracks SET queue = ? WHERE id = ?', (float(queue), int(track_id), ))
		self.commit()

	def add_file(self, filename, check=True):
		"""
		Adds a file to the database, if it's not there yet. New playlist
		records are created automatically.
		"""
		musicdir = self.config.get_music_dir()
		(playlist, track) = filename.decode('utf-8').split(os.path.sep, 1)
		if check:
			row = self.cursor().execute('SELECT 1 FROM tracks WHERE playlist = ? AND name = ?', (playlist, track, )).fetchone()
			if row is not None:
				return
		t = tags.get(os.path.join(musicdir, filename))
		if t is not None:
			self.cursor().execute('INSERT INTO tracks (playlist, name, artist, title, length, artist_weight, weight, count, last_played, queue) VALUES (?, ?, ?, ?, ?, 1, 1, 0, 0, 0)', (playlist, track, t['artist'], t['title'], t['length'], ))
			log('db: track added: %s/%s' % (playlist, track))
		else:
			log('db: no tags: %s/%s' % (playlist, track))

	def update_files(self):
		"""
		Adds to the database all files which are supported by mutagen and have tags.
		"""
		try:
			# Файлы, существующие в ФС.
			infs = []
			musicdir = self.config.get_music_dir()
			for triple in os.walk(musicdir, followlinks=True):
				for fn in triple[2]:
					f = os.path.join(triple[0], fn)[len(musicdir)+1:]
					if os.path.sep in f:
						infs.append(f)

			# Файлы, существующие в БД.
			indb = [os.path.join(row[0], row[1]).encode('utf-8') for row in self.cursor().execute('SELECT playlist, name FROM tracks').fetchall()]

			dead = [x for x in indb if x not in infs]
			new  = [x for x in infs if x not in indb]

			cur = self.cursor()
			for filename in new:
				self.add_file(filename, check=False)
			for filename in dead:
				parts = filename.decode('utf-8').split(os.path.sep, 1)
				cur.execute('DELETE FROM tracks WHERE playlist = ? AND name = ?', (parts[0], parts[1], ))
				log('dead file: %s' % filename)

			# add new playlists
			cur.execute('INSERT INTO playlists (name) SELECT DISTINCT playlist FROM tracks WHERE playlist NOT IN (SELECT name FROM playlists)')
			# update artist weights
			for artist, count in cur.execute('SELECT artist, COUNT(*) FROM tracks WHERE weight > 0 GROUP BY artist'):
				self.cursor().execute('UPDATE tracks SET artist_weight = ? WHERE artist = ?', (1.0 / count, artist, ))

			self.commit()
		except Exception, e:
			self.db.rollback()
			raise

	def move_track_to(self, track_id, playlist_name):
		"""
		Moves a track to a different playlist. Moves the file and updates
		the database. Raises exceptions on errors.
		"""
		track = self.get_track_info(track_id)
		if track is None:
			raise Exception(u'No such track.')
		if track['playlist'] == playlist_name:
			raise Exception(u'It\'s already there.')
		musicdir = self.config.get_music_dir()
		if not os.path.exists(os.path.join(musicdir, playlist_name.encode('utf-8'))):
			raise Exception(u'No such playlist: %s' % playlist_name)

		src = os.path.join(musicdir, track['playlist'].encode('utf-8'), track['filename'].encode('utf-8'))
		if not os.path.exists(src):
			raise Exception(u'Source track does not exist (already renamed?)')
		filename = os.path.basename(track['filename'])
		dst = os.path.join(musicdir, playlist_name.encode('utf-8'), filename.encode('utf-8'))
		if os.path.exists(dst):
			raise Exception(u'Target already exists ("%s"; consider using delete).' % os.path.join(playlist_name, filename))

		os.rename(src, dst)

		self.cursor().execute('UPDATE tracks SET playlist = ? WHERE id = ?', (playlist_name, track_id, ))
		self.commit()

	@classmethod
	def connect(cls):
		if cls.instance is None:
			cls.instance = cls()
		return cls.instance.cursor()

	@classmethod
	def execute(cls, *args, **kwargs):
		return cls.connect().execute(*args, **kwargs)

class track:
	def __init__(self, filename=None, artist=None, title=None, length=None, count=None, weight=None):
		self.id = None
		self.filename = filename
		self.artist = artist
		self.title = title
		self.length = length
		self.weight = weight
		self.count = count
		self.last_played = None

	@classmethod
	def load(cls, id):
		"""
		Loads a track by id.
		"""
		o = cls()
		row = db.execute('SELECT id, name, artist, title, length, weight, count, last_played FROM tracks WHERE id = ?', (id,)).fetchone()
		if row is None:
			raise Exception('Track %u does not exist.' % id)
		o.id, o.filename, o.artist, o.title, o.length, o.weight, o.count, o.last_played = row
		return o

	def save(self):
		"""
		Saves any pending changes.
		"""
		db.execute('UPDATE tracks SET name = ?, artist = ?, title = ?, length = ?, weight = ?, count = ?, last_played = ? WHERE id = ?', (self.filename, self.artist, self.title, self.length, self.weight, self.count, self.last_played, self.id))
		comment = 'ardj=1'
		for k in ('weight', 'count', 'last_played'):
			if getattr(self, k):
				comment += ';%s=%s' % (k, getattr(self, k))
		tags.set(os.path.join(config.get_path('musicdir'), self.filename), { 'artist': self.artist, 'title': self.title, 'ardj': comment })
		return self

	@classmethod
	def add(cls, filename):
		"""
		Adds a file to the database.
		"""
		if not os.path.exists(filename):
			raise Exception('File not found: %s' % filename)

		t = cls(weight=1, count=0, filename=cls.hashname(filename))
		print t
		tg = tags.get(filename)
		for k in ('artist', 'title'):
			setattr(t, k, tg[k])
		cls.copy(filename, os.path.join(config.get_path('musicdir'), t.filename))
		return t.save()

	@classmethod
	def hashname(cls, filename):
		h = hashlib.md5(open(filename, 'rb').read()).hexdigest()
		filename = os.path.join(h[0], h[1], h) + os.path.splitext(filename.lower())[1]
		return filename
		target = os.path.join(config.get_path('musicdir'), filename)
		if not os.path.exists(os.path.dirname(target)):
			os.makedirs(os.path.dirname(target), mode=0755)
		return target

	@classmethod
	def copy(cls, src, dst):
		if not os.path.exists(os.path.dirname(dst)):
			os.makedirs(os.path.dirname(dst), mode=0755)
		open(dst, 'wb').write(open(src, 'rb').read())

	@classmethod
	def get_random(cls, playlist=None, repeat=None, skip_artists=None):
		"""
		Returns a random track which is OK to play.
		"""
		sql = 'SELECT id, randomize(id, artist_weight, weight, count) AS w, count FROM tracks WHERE w > 0'
		params = []
		if playlist is not None:
			sql += ' AND playlist = ?'
			params.append(playlist)
		if repeat is not None:
			sql += ' AND count < ?'
			params.append(repeat)
		if skip_artists is not None:
			tsql = []
			for name in skip_artists:
				tsql.apend('?')
				params.append(name)
			sql += ' AND artist NOT IN (%)' % ', '.join(tsql)
		rows = db.execute(sql, params).fetchall()
		if not rows:
			return None
		probability_sum = sum([row[1] for row in rows])
		init_rnd = rnd = random.random() * probability_sum
		for row in rows:
			if rnd < row[1]:
				log('db: track %u(%s) won with p=%.4f s=%.4f r=%.4f c=%u' % (row[0], playlist, row[1], probability_sum, init_rnd, row[2]))
				return cls.load(row[0])
			rnd = rnd - row[1]
		raise Exception(u'This can not happen (could not choose from %u tracks).' % len(rows))

	def __repr__(self):
		x = ''
		for k in ('artist', 'title', 'filename'):
			if hasattr(self, k) and getattr(self, k):
				x += ' %s=%s' % (k, getattr(self, k))
		return '<track%s>' % x
