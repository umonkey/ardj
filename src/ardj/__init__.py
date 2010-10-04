# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import hashlib
import logging
import os
import random
import re
import shutil
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
		self.debug = False
		logging.basicConfig(filename=self.config.get('log', None), level=logging.DEBUG)

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

		track = self.__get_queued_track(cur)
		if track is None:
			track = self.__get_urgent_track(skip, cur)
		if track is None:
			track = self.__get_track_from_playlists(skip, cur)
		if track is None:
			track = self.get_random_track(cur=cur)
			if track is not None:
				logging.debug(u'Picked track %u (last resort).' % track['id'])
		if track is not None:
			track = self.__fix_track_file_name(track, cur)
			track['count'] += 1
			track['last_played'] = int(time.time())
			track = self.check_track_conditions(track)
			track['labels'] = [] # prevent updating of labels
			self.database.update_track(track, cur)
			if scrobble and self.scrobbler:
				self.scrobbler.submit(track)
			track['filepath'] = os.path.join(self.config.get_music_dir(), track['filename']).encode('utf-8')
			self.database.commit() # без этого параллельные обращения будут висеть
		return track

	def __get_queued_track(self, cur):
		"""
		Returns a track from the top of the queue or None.
		"""
		row = cur.execute('SELECT id, track_id FROM queue ORDER BY id LIMIT 1').fetchone()
		if row is not None:
			track = self.get_track_by_id(row[1])
			logging.debug(u'Picked track %u from the top of the queue.' % track['id'])
			cur.execute('DELETE FROM queue WHERE id = ?', (row[0], ))
			return track

	def __get_urgent_track(self, skip, cur):
		"""
		Returns a track from the immediate (urgent) playlist.
		"""
		labels = self.database.get_urgent()
		if labels:
			track = self.get_random_track({'labels':labels}, skip_artists=skip, cur=cur)
			if track:
				logging.debug(u'Picked track %u from the urgent playlist.' % track['id'])
				return track

	def __get_track_from_playlists(self, skip, cur):
		"""
		Returns a track from and active playlist.
		"""
		for playlist in self.get_active_playlists():
			track = self.get_random_track(playlist, repeat=playlist['repeat'], skip_artists=skip, cur=cur)
			if track is not None:
				logging.debug(u'Picked track %u from playlist %s.' % (track['id'], playlist['name']))
				cur.execute('UPDATE playlists SET last_played = ? WHERE name = ?', (int(time.time()), playlist['name']))
				return track

	def __add_labels_filter(self, sql, params, labels):
		if type(labels) != list:
			raise Exception('Labels must be a list.')
		normal = [l for l in labels if not l.startswith('+') and not l.startswith('-')]
		if normal:
			sql += ' AND id IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(normal))
			for label in normal:
				params.append(label)
		forbidden = [l[1:] for l in labels if l.startswith('-')]
		if forbidden:
			sql += ' AND id NOT IN (SELECT track_id FROM labels WHERE label IN (%s))' % ', '.join(['?'] * len(forbidden))
			for label in forbidden:
				params.append(label)
		required = [l[1:] for l in labels if l.startswith('+')]
		if required:
			for label in required:
				sql += ' AND id IN (SELECT track_id FROM labels WHERE label = ?)'
				params.append(label)
		return sql, params

	def __fix_track_file_name(self, track, cur):
		"""
		Makes sure the file name is MD5 based.
		"""
		if not re.match('[0-9a-f]/[0-9a-f]/[0-9a-f]{32}', os.path.splitext(track['filename'])[0]):
			current_path = os.path.join(self.config.get_music_dir(), track['filename']).encode('utf-8')
			new_name = self.__get_local_file_name(current_path)
			new_path = os.path.join(self.config.get_music_dir(), new_name)
			new_dir = os.path.dirname(new_path)
			if not os.path.exists(new_dir):
				logging.debug(u'Creating folder ' + new_dir)
				os.makedirs(new_dir)
			try:
				shutil.move(current_path, new_path)
				logging.info(u'Moved %s to %s' % (track['filename'], new_name))
				track['filename'] = new_name
				# This can be done later, but can be not, so let's do it to avoid desync.
				cur.execute('UPDATE tracks SET filename = ? WHERE id = ?', (new_name, track['id'], ))
			except:
				logging.info(u'Could move %s to %s' % (track['filename'], new_name))
		return track

	def queue_track(self, id, cur=None):
		"""
		Adds a track to the end of the queue.
		"""
		return (cur or self.database.cursor()).execute('INSERT INTO queue (track_id) VALUES (?)', (id, )).lastrowid

	def check_track_conditions(self, track):
		"""
		Updates track information according to various conditions. Currently
		can only move it to another playlist when play count reaches the limit
		for the current playlist; the target playlist must be specified in
		current playlist's "on_repeat_move_to" property.
		"""
		playlist = None # self.get_playlist_by_name(track['playlist']) # FIXME
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
		return list(set([row[0] for row in cur.execute('SELECT artist FROM tracks WHERE artist IS NOT NULL AND last_played IS NOT NULL ORDER BY last_played DESC LIMIT ' + str(self.config.get('dupes', 5))).fetchall()]))

	def get_last_track(self):
		"""
		Returns a dictionary that describes the last played track.
		"""
		cur = self.database.cursor()
		row = cur.execute('SELECT id, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks ORDER BY last_played DESC LIMIT 1').fetchone()
		if row is not None:
			result = { 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'length': row[4], 'artist_weight': row[5], 'weight': row[6], 'count': row[7], 'last_played': row[8] }
			result['labels'] = [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (result['id'], )).fetchall()]
			return result

	def get_track_by_id(self, id, cur=None):
		"""
		Returns a dictionary that describes the specified track.
		"""
		cur = cur or self.database.cursor()
		row = cur.execute('SELECT id, filename, artist, title, length, artist_weight, weight, count, last_played FROM tracks WHERE id = ?', (id, )).fetchone()
		if row is not None:
			result = { 'id': row[0], 'filename': row[1], 'artist': row[2], 'title': row[3], 'length': row[4], 'artist_weight': row[5], 'weight': row[6], 'count': row[7], 'last_played': row[8] }
			result['labels'] = [row[0] for row in cur.execute('SELECT DISTINCT label FROM labels WHERE track_id = ? ORDER BY label', (id, )).fetchall()]
			return result

	def get_random_track(self, playlist=None, repeat=None, skip_artists=None, cur=None, labels=None):
		"""
		Returns a random track from the specified playlist.  Playlist is a
		dictionary which corresponds to a part of playlists.yaml.  If it has
		labels, they are used, otherwise playlist name is used as the label.
		"""
		cur = cur or self.database.cursor()
		if playlist:
			labels = playlist.has_key('labels') and playlist['labels'] or [playlist['name']]
		else:
			labels = None
		id = self.get_random_track_id(labels, repeat, skip_artists, cur)
		if id is not None:
			return self.get_track_by_id(id, cur)

	def get_random_track_id(self, labels=None, repeat=None, skip_artists=None, cur=None):
		"""
		Returns a random track's id.
		"""
		cur = cur or self.database.cursor()
		sql = 'SELECT id, randomize(id, artist_weight, weight, count) AS w, count FROM tracks WHERE w > 0'
		params = []
		# filter by labels
		if labels:
			sql, params = self.__add_labels_filter(sql, params, labels)
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
		self.database.debug(sql, params)
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
		logging.error(u'Could not choose from %u tracks.' % len(rows))
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
					logging.error(u'Bad playlist: %s: %s' % (e, item))
					logging.error(traceback.format_exc(e))

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
			logging.warning(u'Track no longer exists: %s.' % filename)
			cur.execute('DELETE FROM tracks WHERE filename = ?', (filename.decode('utf-8'), ))

		# Добавляем новые файлы.
		for filename in news:
			self.add_file(filename)

		# Обновление статистики исполнителей.
		for artist, count in cur.execute('SELECT artist, COUNT(*) FROM tracks WHERE weight > 0 GROUP BY artist'):
			cur.execute('UPDATE tracks SET artist_weight = ? WHERE artist = ?', (1.0 / count, artist, ))

		self.update_playlists(cur=cur)

		msg = u'%u files added, %u removed.' % (len(news), len(dead))
		logging.info(u'sync: ' + msg)
		self.database.commit()
		return msg

	def add_file(self, source_filename, properties=None, queue=False):
		"""
		Adds a file to the database or updates it.  Properties, if specified,
		must be a dictionary with keys: owner (email), labels (list), artist,
		title.

		The file is copied to an internal location, the original file can be
		removed afterwards.
		"""
		if not os.path.exists(source_filename):
			raise Exception('File not found.')
		filename = self.__get_local_file_name(source_filename)
		filepath = os.path.join(self.config.get_music_dir(), filename)

		if not os.path.exists(filepath):
			logging.debug(u'Copying the uploaded file to %s' % filepath)
			dirname = os.path.dirname(filepath)
			if not os.path.exists(dirname):
				os.makedirs(dirname)
			shutil.copyfile(source_filename, filepath)

		cur = self.database.cursor()
		properties = self.__get_track_properties(filepath, properties)
		properties['filename'] = filename
		properties['id'] = self.__get_track_id(filename, cur)
		self.database.update_track(properties, cur=cur)
		if queue:
			owner = properties.has_key('owner') and properties['owner'] or 'nobody@nowhere.com'
			cur.execute('INSERT INTO queue (track_id, owner) SELECT id, ? FROM tracks WHERE id NOT IN (SELECT track_id FROM queue) AND id = ?', (owner, properties['id'], ))
		return properties['id']

	def __get_local_file_name(self, filename):
		"""
		Returns an MD5 based file name.
		"""
		f = open(filename, 'rb')
		m = hashlib.md5()
		while True:
			data = f.read(16384)
			if not data:
				break
			m.update(data)
		name = m.hexdigest() + os.path.splitext(filename)[1].lower()
		return os.path.join(name[0], name[1], name)

	def __get_track_id(self, filename, cur):
		"""
		Returns a new track id or the existing one.
		"""
		logging.debug('Looking for an id for file %s' % filename)
		row = cur.execute('SELECT id FROM tracks WHERE filename = ?', (filename, )).fetchone()
		if row:
			logging.debug(u'Reusing track id %u.' % row[0])
			return row[0]
		track_id = cur.execute('INSERT INTO tracks (artist) VALUES (NULL)').lastrowid
		logging.debug(u'New track id is %u.' % track_id)
		return track_id

	def __get_track_properties(self, filepath, properties):
		props = {
			'artist': 'Unknown Artist',
			'title': 'Untitled',
			'length': 0,
			'weight': 1.0,
			'count': 0,
		}
		if type(properties) == dict:
			props.update(properties)
		tg = tags.get(filepath)
		if tg is not None:
			for k in props.keys():
				if k in tg:
					props[k] = tg[k]
		return props

	def backup_track_data(self, args):
		cur = self.database.cursor()
		filename, artist, title, weight, count, last_played = cur.execute('SELECT filename, artist, title, weight, count, last_played FROM tracks WHERE id = ?', (args['id'], )).fetchone()
		comment = u'ardj=1;weight=%f;count=%u;last_played=%s' % (weight, count, last_played)
		try:
			tags.set(os.path.join(self.config.get_music_dir(), filename.encode('utf-8')), { 'artist': artist, 'title': title, 'ardj': comment })
		except Exception, e:
			logging.error(u'Could not write metadata to %s: %s' % (filename, e))

	def sqlite_randomize(self, id, artist_weight, weight, count):
		"""
		Implements the SQLite randomize() function.
		"""
		result = weight or 0
		if artist_weight is not None:
			result = result * artist_weight
		# Fading priorities are disabled for now, would be nice to define this
		# behaviour in playlist.yaml.
		## result = result / ((count or 0) + 1)
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
