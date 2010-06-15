# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import random
import sys
import time
import traceback

import ardj.config as config
import ardj.database as database
import ardj.scrobbler as scrobbler
import ardj.tags as tags

have_jabber = False

class ardj:
	def __init__(self):
		self.config = config.Open()
		self.database = database.Open(self.config.get_db_name())
		self.scrobbler = scrobbler.Open(self.config)

	def __del__(self):
		self.close()

	def get_next_track(self, scrobble=True):
		"""
		Returns information about the next track. The track is chosen from the
		active playlists. If nothing could be chosen, a random track is picked
		regardless of the playlist (e.g., the track can be in no playlist or
		in an unexisting one).  If that fails too, None is returned.

		Normally returns a dictionary with keys that corresponds to the "tracks"
		table fields, e.g.: filename, artist, title, length, artist_weight, weight,
		count, last_played, playlist.  An additional key is filepath, which
		contains the full path name to the picked track, encoded in UTF-8.

		Before the track is returned, its and the playlist's statistics are updated.
		"""
		cur = self.database.cursor()
		# Last played artist names.
		skip = self.get_last_artists(cur=cur)

		track = None
		for playlist in self.get_active_playlists():
			track = self.get_random_track(playlist['name'], repeat=playlist['repeat'], skip_artists=skip, cur=cur)
			if track is not None:
				break
		if track is None:
			track = self.get_random_track(cur=cur)
			if track is not None:
				print >>sys.stderr, 'warning: no tracks in playlists, picked a totally random one.'
		if track is not None:
			track['count'] += 1
			track['last_played'] = int(time.time())
			track = self.check_track_conditions(track)
			self.update_track(track)
			if scrobble and self.scrobbler:
				self.scrobbler.submit(track)
			track['filepath'] = os.path.join(self.config.get_music_dir(), track['filename']).encode('utf-8')
			cur.execute('UPDATE playlists SET last_played = ? WHERE name = ?', (int(time.time()), track['playlist']))
			self.database.commit() # без этого параллельные обращения будут висеть
		return track

	def check_track_conditions(self, track):
		"""
		Updates track information according to various conditions. Currently can
		only move it to another playlist when play count reaches the limit for
		the current playlist; the target playlist must be specified in current
		playlist's "on_repeat_move_to" property.
		"""
		playlist = self.get_playlist_by_name(track['playlist'])
		if playlist:
			if playlist.has_key('repeat') and playlist['repeat'] == track['count']:
				if playlist.has_key('on_repeat_move_to'):
					track['playlist'] = playlist['on_repeat_move_to']
		return track

	def get_playlist_by_name(self, name):
		for playlist in self.get_playlists():
			if name == playlist['name']:
				return playlist
		return None

	def get_last_artists(self, cur=None):
		"""
		Returns the names of last played artists.
		"""
		cur = cur or self.database.cursor()
		return [row[0] for row in cur.execute('SELECT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(self.config.get('dupes', 5))).fetchall()]

	def get_last_track(self):
		"""
		Returns a dictionary that describes the last played track.
		"""
		row = self.database.cursor().execute('SELECT id, playlist, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks ORDER BY last_played DESC LIMIT 1').fetchone()
		if row is not None:
			return { 'id': row[0], 'playlist': row[1], 'filename': row[2], 'artist': row[3], 'title': row[4], 'length': row[5], 'artist_weight': row[6], 'weight': row[7], 'count': row[8], 'last_played': row[9] }

	def get_track_by_id(self, id):
		"""
		Returns a dictionary that describes the specified track.
		"""
		row = self.database.cursor().execute('SELECT id, playlist, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks WHERE id = ?', (id, )).fetchone()
		if row is not None:
			return { 'id': row[0], 'playlist': row[1], 'filename': row[2], 'artist': row[3], 'title': row[4], 'length': row[5], 'artist_weight': row[6], 'weight': row[7], 'count': row[8], 'last_played': row[9] }

	def get_random_track(self, playlist=None, repeat=None, skip_artists=None, cur=None):
		"""
		Returns a random track from the specified playlist.
		"""
		cur = cur or self.database.cursor()
		id = self.get_random_track_id(playlist, repeat, skip_artists, cur)
		if id is not None:
			row = cur.execute('SELECT id, playlist, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks WHERE id = ?', (id, )).fetchone()
			if row is not None:
				return { 'id': row[0], 'playlist': row[1], 'filename': row[2], 'artist': row[3], 'title': row[4], 'length': row[5], 'artist_weight': row[6], 'weight': row[7], 'count': row[8], 'last_played': row[9] }

	def get_random_track_id(self, playlist=None, repeat=None, skip_artists=None, cur=None):
		"""
		Returns a random track's id.
		"""
		cur = cur or self.database.cursor()
		sql = 'SELECT id, randomize(id, artist_weight, weight, count) AS w, count FROM tracks WHERE w > 0'
		params = []
		# filter by playlist
		if playlist is not None:
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
		rows = cur.execute(sql, tuple(params)).fetchall()
		if not rows:
			return None
		# pick a random track
		probability_sum = sum([row[1] for row in rows])
		init_rnd = rnd = random.random() * probability_sum
		for row in rows:
			if rnd < row[1]:
				return row[0]
			rnd = rnd - row[1]
		print >>sys.stderr, 'This must not happen: could not choose from %u tracks.' % len(rows)
		return None

	def get_playlists(self):
		"""
		Returns information about all known playlists.
		"""
		return [{ 'name': row[0] or 'playlist-' + str(row[1]), 'id': row[1], 'priority': row[2], 'repeat': row[3], 'delay': row[4], 'hours': row[5] and [int(x) for x in row[5].split(',')] or None, 'days': row[6] and [int(x) for x in row[6].split(',')] or None, 'last_played': row[7] } for row in self.database.cursor().execute('SELECT name, id, priority, repeat, delay, hours, days, last_played FROM playlists ORDER BY priority DESC').fetchall()]

	def explain_playlists(self):
		self.get_active_playlists(explain=True)

	def get_active_playlists(self, explain=False):
		"""
		Returns a dictionary with currently active playlists.
		"""
		def is_active(playlist):
			if not playlist['priority']:
				if explain: print '%s: zero priority' % playlist['name']
				return False
			if playlist['delay'] and playlist['last_played'] and playlist['delay'] * 60 + playlist['last_played'] > int(time.time()):
				if explain: print '%s: delayed' % playlist['name']
				return False
			if playlist['hours']:
				now = int(time.strftime('%H'))
				if now not in playlist['hours']:
					if explain: print '%s: wrong hour (%s vs %s)' % (playlist['name'], now, playlist['hours'])
					return False
			if playlist['days']:
				day = int(time.strftime('%w')) or 7
				if day not in playlist['days']:
					if explain: print '%s: wrong day (%s vs %s)' % (playlist['name'], day, playlist['days'])
					return False
			if explain: print '%s: ready' % playlist['name']
			return True
		return [p for p in self.get_playlists() if is_active(p)]

	def update_playlists(self, cur=None):
		"""
		Reads playlists.yaml from the files folder and updates the playlists table.
		"""
		cur = cur or self.database.cursor()
		cur.execute('UPDATE playlists SET priority = 0')

		saved = dict([(x['name'], x) for x in self.get_playlists()])

		# Сбрасываем приоритеты, чтобы потом удалить лишние плейтисты.
		for k in saved.keys():
			saved[k]['priority'] = 0

		playlists = self.config.get_playlists()
		if playlists is not None:
			priority = len(playlists) + 1
			for item in playlists:
				try:
					if not saved.has_key(item['name']):
						# создаём новый плейлист
						saved[item['name']] = { 'name': item['name'], 'last_played': None, 'id': cur.execute('INSERT INTO playlists (name) VALUES (NULL)').lastrowid }
					else:
						# очищаем почти все свойства
						saved[item['name']] = { 'name': item['name'], 'id': saved[item['name']]['id'], 'last_played': saved[item['name']]['last_played'] }
					for k in ('days', 'hours'):
						if k in item:
							saved[item['name']][k] = item[k] and ','.join([str(x) for x in item[k]]) or None
					for k in ('repeat', 'delay'):
						if k in item:
							saved[item['name']][k] = int(item[k])
					saved[item['name']]['priority'] = priority
					self.database.update('playlists', saved[item['name']], cur)
					priority -= 1
				except Exception, e:
					print >>sys.stderr, 'bad playlist: %s: %s' % (e, item)
					traceback.print_exc()

		for k in [x for x in saved.keys() if not saved[x]['priority']]:
			cur.execute('DELETE FROM playlists WHERE id = ?', (saved[k]['id'], ))

	def close(self):
		"""
		Flushes any transactions, closes the database.
		"""
		self.database.commit()
		self.config.close()

	def sync(self):
		"""
		Adds new tracks to the database, removes dead ones.
		"""
		cur = self.database.cursor()

		# Файлы, существующие в файловой системе.
		infs = []
		musicdir = self.config.get_music_dir()
		for triple in os.walk(musicdir, followlinks=True):
			for fn in triple[2]:
				f = os.path.join(triple[0], fn)[len(musicdir)+1:]
				if os.path.sep in f:
					infs.append(f)

		# Файлы, существующие в базе данных.
		indb = [row[0].encode('utf-8') for row in cur.execute('SELECT filename FROM tracks').fetchall()]

		news = [x for x in infs if x not in indb]
		dead = [x for x in indb if x not in infs]

		# Удаляем из базы данных несуществующие файлы.
		for filename in dead:
			print >>sys.stderr, 'no longer exists: ' + filename
			cur.execute('DELETE FROM tracks WHERE filename = ?', (filename.decode('utf-8'), ))

		# Добавляем новые файлы.
		for filename in news:
			self.add_track_from_file(filename)

		# Обновление статистики исполнителей.
		for artist, count in cur.execute('SELECT artist, COUNT(*) FROM tracks WHERE weight > 0 GROUP BY artist'):
			cur.execute('UPDATE tracks SET artist_weight = ? WHERE artist = ?', (1.0 / count, artist, ))

		self.update_playlists(cur=cur)

		msg = u'%u files added, %u removed.' % (len(news), len(dead))
		print >>sys.stderr, 'sync: ' + msg
		self.database.commit()
		return msg

	def add_track_from_file(self, filename):
		"""
		Добавление файла в базу данных.
		"""
		cur = self.database.cursor()
		filepath = os.path.join(self.config.get_music_dir(), filename)

		if cur.execute('SELECT id FROM tracks WHERE filename = ?', (filename.decode('utf-8'), )).fetchone():
			print >>sys.stderr, 'refusing to add %s again' % filename
			return False

		tg = tags.get(filepath)
		if tg is None:
			print >>sys.stderr, 'skipped: ' + filename
			return False

		args = {
			'filename': filename.decode('utf-8'),
			'artist': tg['artist'],
			'title': tg['title'],
			'length': tg['length'], # in seconds
			'count': 0,
			'weight': 1.0,
			'last_played': None,
			'playlist': filename.split(os.path.sep)[0].decode('utf-8'),
		}

		# Загрузка сохранённых метаданных.
		if tg.has_key('ardj') and tg['ardj'] is not None:
			saved = dict([x.split('=') for x in tg['ardj'].split(';')])
			if saved.has_key('ardj') and saved['ardj'] == '1':
				try:
					if saved.has_key('count'):
						args['count'] = int(saved['count'])
					if saved.has_key('last_played') and saved['last_played'] != 'None':
						args['last_played'] = int(saved['last_played'])
					if saved.has_key('weight'):
						args['weight'] = float(saved['weight'])
					if saved.has_key('playlist'):
						args['playlist'] = unicode(saved['playlist'])
				except Exception, e:
					print >>sys.stderr, 'error parsing metadata from %s: %s' % (filename, e)

		# Сохраняем фиктивную запись, чтобы получить id.
		args['id'] = cur.execute('INSERT INTO tracks (playlist) VALUES (NULL)').lastrowid

		self.update_track(args, backup=False, cur=cur)
		print >>sys.stderr, 'added: ' + filename
		return True

	def update_track(self, args, backup=True, cur=None, commit=True):
		if type(args) != dict:
			raise TypeError('ardj.update_track() expects a dictionary.')

		if cur is None:
			cur = self.database.cursor()

		sql = []
		params = []
		for k in args:
			if k != 'id':
				sql.append(k + ' = ?')
				params.append(args[k])
		params.append(args['id'])

		sql = 'UPDATE tracks SET ' + ', '.join(sql) + ' WHERE id = ?'
		cur.execute(sql, tuple(params))

		if backup:
			filename, artist, title, playlist, weight, count, last_played = cur.execute('SELECT filename, artist, title, playlist, weight, count, last_played FROM tracks WHERE id = ?', (args['id'], )).fetchone()
			comment = u'ardj=1;playlist=%s;weight=%f;count=%u;last_played=%s' % (playlist, weight, count, last_played)
			try:
				tags.set(os.path.join(self.config.get_music_dir(), filename.encode('utf-8')), { 'artist': artist, 'title': title, 'ardj': comment })
			except Exception, e:
				print >>sys.stderr, 'could not write metadata to %s: %s' % (filename.encode('utf-8'), e)

		if commit:
			self.database.commit()

	def sqlite_randomize(self, id, artist_weight, weight, count):
		"""
		Implements the SQLite randomize() function.
		"""
		result = weight or 0
		if artist_weight is not None:
			result = result * artist_weight
		result = result / ((count or 0) + 1)
		return result

	def get_stats(self):
		"""
		Returns information about the database in the form of a dictionary
		with the following keys: tracks, seconds.
		"""
		count, length = 0, 0
		for row in self.database.cursor().execute('SELECT length FROM tracks WHERE weight > 0').fetchall():
			count = count + 1
			if row[0] is not None:
				length = length + row[0]
		return { 'tracks': count, 'seconds': length }

	def get_bot(self):
		"""
		Returns an instance of the jabber bot.
		"""
		global have_jabber
		if not have_jabber:
			import ardj.jabber as jabber
			have_jabber = True
		return jabber.Open(self)

def Open():
    return ardj()
