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

class ardj:
	def __init__(self):
		self.config = config.Open()
		self.database = database.Open(self.config.get_db_name())
		self.scrobbler = scrobbler.Open(self.config)

	def __del__(self):
		# print >>sys.stderr, 'Shutting down.'
		self.database.commit()

	def next(self, scrobble=True):
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
		skip = [row[0] for row in cur.execute('SELECT DISTINCT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(self.config.get('dupes', 5))).fetchall()]

		track = None
		playlists = self.get_active_playlists()
		for name in playlists:
			track = self.get_random_track(name, repeat=playlists[name]['repeat'], skip_artists=skip, cur=cur)
			if track is not None:
				break
		if track is None:
			track = self.get_random_track(cur=cur)
			if track is not None:
				print >>sys.stderr, 'warning: no tracks in playlists, picked a totally random one.'
		if track is not None:
			track['count'] += 1
			track['last_played'] = int(time.time())
			self.update_track(track)
			if scrobble and self.scrobbler:
				self.scrobbler.submit(track)
			track['filepath'] = os.path.join(self.config.get_music_dir(), track['filename']).encode('utf-8')
			self.database.commit() # без этого параллельные обращения будут висеть
		return track

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
		return dict([(row[0] or 'playlist-' + str(row[1]), { 'id': row[1], 'priority': row[2], 'repeat': row[3], 'delay': row[4], 'hours': row[5] and [int(x) for x in row[5].split(',')] or None, 'days': row[6] and [int(x) for x in row[6].split(',')] or None, 'last_played': row[7] }) for row in self.database.cursor().execute('SELECT name, id, priority, repeat, delay, hours, days, last_played FROM playlists').fetchall()])

	def get_active_playlists(self):
		"""
		Returns a dictionary with currently active playlists.
		"""
		def is_active(playlist):
			if not playlist['priority']:
				return False
			if playlist['delay'] and playlist['last_played'] and playlist['delay'] * 60 + playlist['last_played'] > int(time.time()):
				return False
			if playlist['hours']:
				if '%u' % int(time.strftime('%H')) not in playlist['hours']:
					return False
			if playlist['days']:
				day = time.strftime('%w') or '7'
				if day not in playlist['days']:
					return False
			return True
		saved = self.get_playlists()
		for k in saved.keys():
			if not is_active(saved[k]):
				del(saved[k])
		return saved

	def update_playlists(self):
		"""
		Reads playlists.yaml from the files folder and updates the playlists table.
		"""
		cur = self.database.cursor()
		cur.execute('UPDATE playlists SET priority = 0')

		saved = self.get_playlists()

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

	def delete(self, id=None):
		"""
		Deletes a track.  If id is not specified, deletes the
		currently played track.
		"""
		pass

	def set(self, attrs):
		"""
		Modifies track properties.  Attrs is a dictionary with properties
		to modify.  If there is no 'id' property, the currently played
		track is modified.  Updated information is saved to both database
		and file tags.
		"""
		pass

	def update(self):
		"""
		Updates the database by scanning files.
		"""
		pass

	def close(self):
		"""
		Flushes any transactions, closes the database.
		"""
		pass

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

		print >>sys.stderr, 'sync: %u new files, %u dead ones.' % (len(news), len(dead))
		self.database.commit()

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

	def update_track(self, args, backup=True, cur=None):
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

def Open():
    return ardj()
