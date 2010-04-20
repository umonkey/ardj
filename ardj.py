#!/usr/bin/env python
# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import sys
import time
import traceback

try:
	import yaml
except ImportError:
	print >>sys.stderr, 'Please install PyYAML (python-yaml).'
	sys.exit(13)

try:
	from sqlite3 import dbapi2 as sqlite
	from sqlite3 import OperationalError
except ImportError:
	print >>sys.stderr, 'Please install pysqlite2.'
	sys.exit(13)

class ardb:
	def __init__(self, name):
		isnew = not os.path.exists(name)
		self.file_name = name
		self.db = sqlite.connect(self.file_name)
		if isnew:
			cur = self.db.cursor()
			cur.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT, last_played INTEGER)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_playlists_last ON playlists (last_played)')
			cur.execute('CREATE TABLE IF NOT EXISTS tracks (playlist TEXT, name TEXT, count INTEGER, last_played INTEGER, queue INTEGER)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON tracks (playlist)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_queue ON tracks (queue)')

	def cursor(self):
		return self.db.cursor()

	def commit(self):
		self.db.commit()

class ardj:
	def __init__(self, path):
		self.path = path
		self.config = self.read_config()
		self.db = ardb(os.path.join(self.path, 'ardj.sqlite'))

	def read_config(self):
		name = os.path.join(self.path, 'ardj.yaml')
		config = yaml.load(open(name, 'r').read())
		for k in ['playlists']:
			if not config.has_key(k):
				raise Exception('No "%s\" key in %s.' % (k, name))
		return config

	def log_error(self, message):
		if '-q' not in sys.argv:
			print >>sys.stderr, message

	def get_playlists(self):
		"""
		Returns all unblocked playlists.
		"""
		stats = self.get_playlist_stats()
		playlists = []
		if self.config.has_key('playlists'):
			for playlist in self.config['playlists']:
				if playlist.has_key('name'):
					dir = os.path.join(self.path, playlist['name'])
					if not stats.has_key(playlist['name']):
						pass # self.log_error('Playlist %s not in the database (add with ardj -u)' % playlist['name'])
					elif not os.path.exists(dir):
						self.log_error('Playlist %s folder does not exist.' % playlist['name'])
					elif not os.path.isdir(dir):
						self.log_error('Playlist %s does not point to a folder.' % playlist['name'])
					elif playlist.has_key('delay') and (playlist['delay'] * 60) + stats[playlist['name']] > int(time.time()):
						self.log_error('Playlist %s is delayed.' % playlist['name'])
					elif playlist.has_key('hours') and not self.in_list(int(time.strftime('%H')), playlist['hours']):
						self.log_error('Playlist %s is not active on this hour.' % playlist['name'])
					elif playlist.has_key('days') and not self.in_list(self.get_current_day_number(), playlist['days']):
						self.log_error('Playlist %s is not active on this day.' % playlist['name'])
					else:
						playlists.append(playlist)
		return playlists

	def in_list(self, value, lst):
		if type(lst) != type([]):
			lst = list(lst)
		return value in lst

	def get_current_day_number(self):
		return int(time.strftime('%w')) or 7

	def get_playlist_stats(self):
		"""
		Returns last played times for playlists, in the form of a dictionary.
		"""
		res = {}
		cur = self.db.cursor().execute('SELECT name, last_played FROM playlists')
		for row in cur.fetchall() or []:
			res[row[0]] = row[1]
		return res

	def pick_track_unsafe(self):
		"""
		Prints the name of a random track.
		"""
		for playlist in self.get_playlists():
			if playlist.has_key('repeat'):
				cur = self.db.cursor().execute('SELECT name, count FROM tracks WHERE playlist = ? AND count < ? ORDER BY queue DESC, RANDOM() LIMIT 1', (playlist['name'], playlist['repeat'], ))
			else:
				cur = self.db.cursor().execute('SELECT name, count FROM tracks WHERE playlist = ? ORDER BY queue DESC, RANDOM() LIMIT 1', (playlist['name'], ))
			track = cur.fetchone()
			if track is not None:
				now = int(time.time())
				cur.execute('UPDATE tracks SET count = ?, last_played = ?, queue = 0 WHERE playlist = ? AND name = ?', (track[1] + 1, now, playlist['name'], track[0], ))
				cur.execute('UPDATE playlists SET last_played = ? WHERE name = ?', (now, playlist['name'], ))
				self.db.commit()
				self.log_track(os.path.join(playlist['name'], track[0]))
				return os.path.realpath(os.path.join(self.path, playlist['name'], track[0])).encode('utf-8')

		print >>sys.stderr, 'No tracks. Add some, then ardj -u.'
		sys.exit(1)

	def pick_track(self):
		retries = 10
		while retries:
			try:
				filename = self.pick_track_unsafe()
				if filename is not None and os.path.exists(filename):
					return filename
			except: pass
		print >>sys.stderr, 'Could not find a file in 10 attempts.'

	def log_track(self, filename):
		try:
			msg = '%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), filename.encode('utf-8'))
			# full log
			f = open(os.path.join(self.path, 'ardj.log'), 'a').write(msg)
			# short log
			logname = os.path.join(self.path, 'ardj.short.log')
			if os.path.exists(logname):
				lines = '\n'.join((open(logname, 'r').read() + msg).split('\n')[-20:])
			else:
				lines = msg
			open(logname, 'w').write(lines)
		except: pass

	def update_db(self):
		"""
		Scans the folder for new music. Adds new folders and files to the
		database, reports the progress in stdout. Treats all folders as
		playlists, not only those listed in the config file. Only treats
		MP3 files as tracks.
		"""
		cur = self.db.cursor()
		existing = [os.path.join(r[0], r[1]) for r in cur.execute('SELECT playlist, name FROM tracks').fetchall()]
		for dir in os.listdir(self.path):
			if os.path.isdir(os.path.join(self.path, dir)):
				if cur.execute('SELECT id FROM playlists WHERE name = ?', (dir, )).fetchone() is None:
					print '+ %s/' % dir
					cur.execute('INSERT INTO playlists (name, last_played) VALUES (?, 0)', (dir, ))
				for file in self.get_files_in_folder(dir):
					try:
						file = file.decode('utf-8')
						if file.lower().endswith('.mp3'):
							if os.path.join(dir, file) not in existing:
								cur.execute('INSERT INTO tracks (playlist, name, count, last_played, queue) VALUES (?, ?, ?, ?, ?)', (dir, file, 0, 0, 0, ))
								print '+ %s/%s' % (dir, file)
					except Exception, e:
						print '? %s/%s (error)' % (dir, file)
		for file in existing:
			if not os.path.exists(os.path.join(self.path, file)):
				(playlist, name) = os.path.split(file)
				cur.execute('DELETE FROM tracks WHERE playlist = ? AND name = ?', (playlist, name, ))
				print '- %s' % file
		self.db.commit()

	def get_files_in_folder(self, folder_name):
		lst = []
		prefixlen = len(os.path.join(self.path, folder_name)) + 1
		for triple in os.walk(os.path.join(self.path, folder_name), followlinks=True):
			for fn in triple[2]:
				lst.append(os.path.join(triple[0], fn)[prefixlen:])
		return lst

def usage():
	print >>sys.stderr, 'Usage: %s working_dir options...' % sys.argv[0]
	print >>sys.stderr, 'Options:'
	print >>sys.stderr, '  -n    show next track'
	print >>sys.stderr, '  -q    turn off most messages'
	print >>sys.stderr, '  -u    update database'
	sys.exit(2)

def main(argv):
	try:
		paths = [x for x in argv[1:] if os.path.exists(x)]
		if not paths:
			usage()
		elif not os.path.exists(os.path.join(paths[0], 'ardj.yaml')):
			raise Exception('No ardj.yaml in %s' % paths[0])

		a = ardj(paths[0].rstrip(os.path.sep))
		if '-u' in argv:
			a.update_db()
		elif '-n' in argv:
			print a.pick_track()
		else:
			usage()
	except Exception, e:
		print >>sys.stderr, str(e)
		traceback.print_exc()
		sys.exit(1)

if __name__ == '__main__':
	sys.exit(main(sys.argv))
