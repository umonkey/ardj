# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:
#
# database related functions for ardj.
#
# ardj is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# ardj is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Functions for working with the database.

This module can be used as a command line script, in which case
the music dir is watched for updates.
"""

import hashlib
import os
import random
import sys
import time
import traceback

import notify
import replaygain
import scrobbler
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
	_instance = None

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
			playlist.init_db(cur)
			track.init_db(cur)
		self.scrobbler = scrobbler.client()

	@classmethod
	def instance(cls):
		if cls._instance is None:
			cls._instance = cls()
		return cls._instance

	def sqlite_randomize(self, id, artist_weight, weight, count):
		"""
		The randomize() function for SQLite.
		"""
		try:
			result = weight

			# применяем коэффициент исполнителя (= 1 / количество_дорожек)
			if artist_weight is not None:
				result = result * artist_weight

			# делим на количество проигрываний, чтобы стимулировать
			# дорожки, которые проигрываются реже
			result = result / (count + 1)

			# log('randomize(%05u, %f, %f, %u) = %f' % (id, artist_weight, weight, count, result))
			return result
		except Exception, e:
			log('sqlite: randomize() exception: %s' % e, trace=True)
			return None

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

	def get_stats(self):
		count, length = 0, 0
		for row in self.cursor().execute('SELECT length FROM tracks WHERE weight > 0').fetchall():
			count = count + 1
			if row[0] is not None:
				length = length + row[0]
		return (count, length)

	def set_track_weight(self, track_id, weight):
		self.cursor().execute('UPDATE tracks SET weight = ? WHERE id = ?', (float(weight), int(track_id), ))
		self.commit()

	def update(self):
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
			indb = [row[0].encode('utf-8') for row in self.cursor().execute('SELECT filename FROM tracks').fetchall()]

			dead = [x for x in indb if x not in infs]
			new  = [x for x in infs if x not in indb]

			cur = self.cursor()
			track.add(new)
			for filename in dead:
				cur.execute('DELETE FROM tracks WHERE filename = ?', (filename.decode('utf-8'), ))
				log('dead file: %s' % filename)

			# add new playlists
			self.update_playlists()
			# cur.execute('INSERT INTO playlists (name) SELECT DISTINCT playlist FROM tracks WHERE playlist NOT IN (SELECT name FROM playlists)')

			# update artist weights
			for artist, count in cur.execute('SELECT artist, COUNT(*) FROM tracks WHERE weight > 0 GROUP BY artist'):
				self.cursor().execute('UPDATE tracks SET artist_weight = ? WHERE artist = ?', (1.0 / count, artist, ))

			self.commit()
		except Exception, e:
			self.db.rollback()
			raise

	def update_playlists(self):
		"""
		Reads playlists.yaml from the files folder and updates the playlists table.
		"""
		cur = self.cursor()
		cur.execute('UPDATE playlists SET priority = 0')

		playlists = self.config.get_playlists()
		if playlists is not None:
			priority = len(playlists) + 1
			for item in playlists:
				try:
					obj = playlist.load_by_name(item['name'])
					obj.priority = priority
					for k in ('days', 'hours'):
						if k in item:
							setattr(obj, k, item[k])
					for k in ('repeat', 'delay'):
						if k in item:
							setattr(obj, k, int(item[k]))
					obj.save(cur)
					priority -= 1
				except Exception, e:
					print >>sys.stderr, 'Bad playlist: %s: %s' % (e, item)
					traceback.print_exc()

			cur.execute('DELETE FROM playlists WHERE priority = 0')
			log('%u playlists saved.' % len(playlists))
			self.commit()

	@classmethod
	def execute(cls, *args, **kwargs):
		return cls.instance().cursor().execute(*args, **kwargs)

class playlist:
	"""
	Represents a playlist.
	"""
	def __init__(self):
		self.id = None
		self.priority = 0
		self.name = None
		self.repeat = None
		self.delay = None
		self.hours = None
		self.days = None
		self.last_played = None

	def __repr__(self):
		r = '<playlist'
		for k in ('id', 'priority', 'name', 'repeat', 'delay', 'hours', 'days'):
			r += ' %s=%s' % (k, getattr(self, k))
		return r + '>'

	@classmethod
	def load_by_name(cls, name):
		pl = [x for x in cls.get_all() if x.name == name]
		if pl: return pl[0]
		pl = cls()
		pl.name = name
		return pl

	@classmethod
	def get_all(cls):
		"""
		Returns all available playlists.
		"""
		result = []
		for row in db.execute('SELECT id, priority, name, repeat, delay, hours, days, last_played FROM playlists ORDER BY priority DESC'):
			obj = cls()
			obj.id, obj.priority, obj.name, obj.repeat, obj.delay, obj.hours, obj.days, obj.last_played = row
			for k in ('days', 'hours'):
				if getattr(obj, k): setattr(obj, k, getattr(obj, k).split(','))
				else: setattr(obj, k, None)
			result.append(obj)
		return result

	@classmethod
	def get_active(cls):
		"""
		Returns active playlists.
		"""
		return [p for p in cls.get_all() if p.__isactive__()]

	def save(self, cur=None):
		"""
		Saves the current playlist.
		"""
		if cur is None:
			cur = db.instance().cursor()
		if self.id is None:
			row = cur.execute('SELECT id FROM playlists WHERE name = ?', (self.name, )).fetchone()
			if row is not None:
				self.id = row[0]
			else:
				self.id = cur.execute('INSERT INTO playlists (name) VALUES (NULL)').lastrowid
		fl = lambda l: ','.join([str(x) for x in l or []])
		cur.execute('UPDATE playlists SET priority = ?, name = ?, repeat = ?, delay = ?, hours = ?, days = ?, last_played = ? WHERE id = ?', (self.priority, self.name, self.repeat, self.delay, fl(self.hours), fl(self.days), self.last_played, self.id, ))
		return self

	def mark_played(self):
		"""
		Updates the last played status.
		"""
		self.last_played = int(time.time())
		return self

	@classmethod
	def init_db(cls, db):
		"""
		Creates database tables.
		"""
		log('creating table: playlists')
		db.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, priority REAL, name TEXT, repeat INTEGER, delay INTEGER, hours TEXT, days TEXT, last_played INTEGER)')

	def __isactive__(self):
		"""
		Checks whether the playlist is active.
		"""
		if not self.priority:
			# print >>sys.stderr, '%s not active: zero priority' % self.name
			return False
		if self.delay is not None and self.last_played is not None and self.delay * 60 + self.last_played > int(time.time()):
			# print >>sys.stderr, '%s not active: delayed' % self.name
			return False
		if self.hours is not None:
			if '%u' % int(time.strftime('%H')) not in self.hours:
				# print >>sys.stderr, '%s not active: wrong hours -- %s not in %s' % (self.name, time.strftime('%H'), self.hours)
				return False
		if self.days is not None:
			day = time.strftime('%w') or '7'
			if day not in self.days:
				# print >>sys.stderr, '%s not active: wrong days' % self.name
				return False
		print >>sys.stderr, '%s is active' % self.name
		return True

class track:
	def __init__(self):
		self.id = None
		self.filename = None
		self.artist = None
		self.title = None
		self.playlist = None
		self.length = None
		self.weight = 1.0
		self.count = 0
		self.last_played = None

	@property
	def path(self):
		return os.path.join(config.get_path('musicdir'), self.filename)

	def scrobble(self):
		cli = db.instance().scrobbler
		if cli is not None:
			cli.submit(self)

	@classmethod
	def init_db(cls, db):
		"""
		Creates database tables.
		"""
		db.execute('CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, playlist TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, artist_weight REAL, weight REAL, count INTEGER, last_played INTEGER)')
		db.execute('CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON tracks (playlist)')
		db.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
		db.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')

	@classmethod
	def load(cls, id):
		"""
		Loads a track by id.
		"""
		o = cls()
		row = db.execute('SELECT id, playlist, filename, artist, title, length, weight, count, last_played FROM tracks WHERE id = ?', (id,)).fetchone()
		if row is None:
			raise Exception('Track %s does not exist.' % id)
		o.id, o.playlist, o.filename, o.artist, o.title, o.length, o.weight, o.count, o.last_played = row
		return o

	@classmethod
	def get_all(cls):
		result = []
		for row in db.execute('SELECT id, playlist, filename, artist, title, length, weight, count, last_played FROM tracks'):
			obj = cls()
			obj.id, obj.playlist, obj.filename, obj.artist, obj.title, obj.length, obj.weight, obj.count, obj.last_played = row
			result.append(obj)
		return result

	@classmethod
	def get_last_artists(cls):
		"""
		Returns names of most recently played artists.
		"""
		limit = config.get('artist_history', 5)
		return [row[0] for row in db.execute('SELECT DISTINCT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(limit)).fetchall()]

	@classmethod
	def get_last_tracks(cls, limit=10):
		"""
		Returns last played tracks.
		"""
		return [cls.load(row[0]) for row in db.execute('SELECT id FROM tracks WHERE last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(limit)).fetchall()]

	def save(self, commit=True, backup=True):
		"""
		Saves the current track.
		"""
		if not self.artist:
			self.artist = 'Unknown'
		if not self.title:
			self.title = os.path.basename(self.filename)
		if not self.playlist:
			self.playlist = config.get('default_playlist', os.path.split(self.filename)[0])
			if not self.playlist:
				raise Exception('Saving a track with no playlist.')
		if self.id is None:
			self.id = db.execute('INSERT INTO tracks (playlist) VALUES (NULL)').lastrowid
			log('track added: id=%u filename=%s' % (self.id, self.filename))
		db.execute('UPDATE tracks SET playlist = ?, filename = ?, artist = ?, title = ?, length = ?, weight = ?, count = ?, last_played = ? WHERE id = ?', (self.playlist, self.filename, self.artist, self.title, self.length, self.weight, self.count, self.last_played, self.id))
		if commit:
			db.instance().commit()
		if backup:
			self.backup()
		return self

	def backup(self):
		"""
		Saves track metadata to tags.
		"""
		comment = 'ardj=1'
		for k in ('playlist', 'weight', 'count', 'last_played'):
			comment += ';%s=%s' % (k, getattr(self, k))
		tags.set(os.path.join(config.get_path('musicdir'), self.filename), { 'artist': self.artist, 'title': self.title, 'ardj': comment })

	@classmethod
	def get_random(cls):
		"""
		Returns a random track from the most appropriate playlist.
		"""
		skip_artists = track.get_last_artists()
		playlists = playlist.get_active()
		if not playlists:
			log('db: no active playlists')
			return None

		def find_track(playlists, skip_artists):
			for pl in playlists:
				id = track.__randomid__(pl.name, repeat=pl.repeat, skip_artists=skip_artists)
				if id is not None:
					obj = cls.load(id)
					obj.count += 1
					obj.last_played = int(time.time())
					obj.save()
					pl.mark_played().save()
					return obj

		obj = find_track(playlists, skip_artists)
		if obj is None and skip_artists:
			obj = find_track(playlists, None)
		return obj

	@classmethod
	def __randomid__(cls, playlist=None, repeat=None, skip_artists=None):
		"""
		Returns id of a random track.
		"""
		sql = 'SELECT id, randomize(id, artist_weight, weight, count) AS w, count FROM tracks WHERE w > 0'
		params = []
		# filter by playlist
		if playlist is None:
			sql += ' AND playlist IS NULL'
		else:
			sql += ' AND playlist = ?'
			params.append(playlist)
		# filter by repeat count
		if repeat is not None:
			sql += ' AND count < ?'
			params.append(repeat)
		# filter by recent artists
		if skip_artists is not None:
			tsql = []
			for name in skip_artists:
				tsql.append('?')
				params.append(name)
			sql += ' AND artist NOT IN (' + ', '.join(tsql) + ')'
		# fetch all records
		rows = db.execute(sql, tuple(params)).fetchall()
		if not rows:
			return None
		# pick a random track
		probability_sum = sum([row[1] for row in rows])
		init_rnd = rnd = random.random() * probability_sum
		for row in rows:
			if rnd < row[1]:
				log('db: track %u(%s) won with p=%.4f s=%.4f r=%.4f c=%u' % (row[0], playlist, row[1], probability_sum, init_rnd, row[2]))
				return row[0]
			rnd = rnd - row[1]
		raise Exception(u'This can not happen (could not choose from %u tracks).' % len(rows))

	@classmethod
	def load_by_filename(cls, filename):
		"""
		Finds a track by its filename.
		"""
		if type(filename) == str:
			filename = filename.decode('utf-8')
		row = db.execute('SELECT id FROM tracks WHERE filename = ?', (filename, )).fetchone()
		if row is not None:
			return cls.load(row[0])

	@classmethod
	def add(cls, filenames):
		if type(filenames) != list: filenames = [filenames]
		for filename in filenames:
			obj = cls.from_file(filename)
			if obj is not None and obj.id is None:
				obj.save()
		db.instance().commit() # the whole batch

	@classmethod
	def from_file(cls, filename):
		obj = cls.load_by_filename(filename)
		if obj is not None:
			return obj
		filepath = os.path.join(config.get_path('musicdir'), filename)
		if not os.path.exists(filepath):
			log('file not found: %s' % filename)
			return None
		try:
			obj = cls()
			obj.filename = filename
			if type(obj.filename) == str:
				obj.filename = obj.filename.decode('utf-8')
			replaygain.update(filepath)
			tg = tags.get(filepath)
			if tg is None:
				log('file skipped: %s' % filename)
				return None
			for k in ('artist', 'title', 'length'):
				setattr(obj, k, tg[k])
			if tg.has_key('ardj') and tg['ardj'] is not None:
				saved = dict([x.split('=') for x in tg['ardj'].split(';')])
				if saved.has_key('ardj') and saved['ardj'] == '1':
					del saved['ardj']
					for k in saved:
						if k in ('count', 'last_played'):
							setattr(obj, k, int(saved[k]))
						elif k in ('weight'):
							setattr(obj, k, float(saved[k]))
						else:
							setattr(obj, k, saved[k])
		except Exception, e:
			log('error adding %s: %s' % (filename, e))
			traceback.print_exc()
		return obj

	@classmethod
	def __hashname__(cls, filename):
		"""
		Returns a MD5-based hashed file name.
		"""
		h = hashlib.md5(open(filename, 'rb').read()).hexdigest()
		filename = os.path.join(h[0], h[1], h) + os.path.splitext(filename.lower())[1]
		return filename

	@classmethod
	def monitor(self):
		"""
		Starts tracking the music dir.
		"""
		def callback(action, path):
			localpath = path.decode('utf-8')
			if localpath.startswith(musicdir):
				localpath = localpath[len(musicdir):].lstrip(os.path.sep)
				if action == 'deleted':
					dbi.execute('DELETE FROM tracks WHERE filename = ?', (localpath, ))
					tmp = localpath.rstrip(os.path.sep) + os.path.sep
					dbi.execute('DELETE FROM tracks WHERE filename LIKE ?', (tmp, ))
					dbi.commit()
				# Only track creation of folders, which is a also a case of
				# renaming/moving a folder. Files are created with a zero
				# length and can not be added at this point because there
				# will be no tags. Files are added when they're changed
				# and length is over 16kb.
				elif action == 'created' and os.path.isdir(path):
					dbi.update()
				elif action == 'modified' and os.path.isfile(path):
					if localpath == 'playlists.yaml':
						db.instance().update_playlists()
					elif os.path.getsize(path) > 16384:
						track.add([localpath])
				# else: print 'unhandled:', action, path, localpath

		dbi = db.instance()
		musicdir = config.get_path('musicdir')

		# Synchronize before tracking.
		dbi.update()

		return notify.monitor([musicdir], callback)

	@classmethod
	def __copy__(cls, src, dst):
		"""
		Copies a file creating all necessary dst subfolders.
		"""
		if not os.path.exists(os.path.dirname(dst)):
			os.makedirs(os.path.dirname(dst), mode=0755)
		open(dst, 'wb').write(open(src, 'rb').read())

	def __repr__(self):
		x = ''
		for k in ('id', 'playlist', 'filename', 'artist', 'title'):
			v = getattr(self, k)
			if v:
				if type(v) == unicode:
					v = v.encode('utf-8')
				x += ' %s=%s' % (k, v)
		return '<track%s>' % x

def commit():
	db.instance().commit()

if __name__ == '__main__':
	m = track.monitor()

	print 'Watching files, press Ctrl+C to stop.'
	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		print 'Break.'
	finally:
		m.stop()
