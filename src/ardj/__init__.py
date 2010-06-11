# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import sys
import traceback

import ardj.config as config
import ardj.database as database
import ardj.tags as tags

class ardj:
	def __init__(self):
		self.config = config.Open()
		self.database = database.Open(self.config.get_db_name())

	def __del__(self):
		print >>sys.stderr, 'Shutting down.'

	def next(self):
		"""
		Returns information about the next track.
		"""
		# last played artist names
		cur = self.database.cursor()
		skip = [row[0] for row in cur.execute('SELECT DISTINCT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(self.config.get('dupes', 5))).fetchall()]
		return skip

	def get_active_playlists(self):
		pass

	def update_playlists(self):
		"""
		Reads playlists.yaml from the files folder and updates the playlists table.
		"""
		cur = self.database.cursor()
		cur.execute('UPDATE playlists SET priority = 0')

		saved = dict([(row[0] or 'playlist-' + str(row[1]), { 'id': row[1], 'priority': 0, 'repeat': row[3], 'delay': row[4], 'hours': row[5], 'days': row[6], 'last_played': row[7] }) for row in cur.execute('SELECT name, id, priority, repeat, delay, hours, days, last_played FROM playlists').fetchall()])

		playlists = self.config.get_playlists()
		if playlists is not None:
			priority = len(playlists) + 1
			for item in playlists:
				try:
					if not saved.has_key(item['name']):
						saved[item['name']] = { 'name': item['name'], 'last_played': None, 'id': cur.execute('INSERT INTO playlists (name) VALUES (NULL)').lastrowid }
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

		# Удаляем из базы данных несуществующие файлы.
		for filename in [x for x in indb if x not in infs]:
			print >>sys.stderr, 'no longer exists: ' + filename
			cur.execute('DELETE FROM tracks WHERE filename = ?', (filename.decode('utf-8'), ))

		# Добавляем новые файлы.
		for filename in [x for x in infs if x not in indb]:
			self.add_track_from_file(filename)

		# Обновление статистики исполнителей.
		for artist, count in cur.execute('SELECT artist, COUNT(*) FROM tracks WHERE weight > 0 GROUP BY artist'):
			cur.execute('UPDATE tracks SET artist_weight = ? WHERE artist = ?', (1.0 / count, artist, ))

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
			print >>sys.stderr, 'writing metadata to ' + filename.encode('utf-8')
			filename, artist, title, playlist, weight, count, last_played = cur.execute('SELECT filename, artist, title, playlist, weight, count, last_played FROM tracks WHERE id = ?', (args['id'], )).fetchone()
			comment = u'ardj=1;playlist=%s;weight=%f;count=%u;last_played=%s' % (playlist, weight, count, last_played)
			tags.set(os.path.join(self.config.get_music_dir(), filename.encode('utf-8')), { 'artist': artist, 'title': title, 'ardj': comment })

	def sqlite_randomize(self, id, artist_weight, weight, count):
		result = weight or 0
		if artist_weight is not None:
			result = result * artist_weight
		result = result / ((count or 0) + 1)
		return result

def Open():
    return ardj()
