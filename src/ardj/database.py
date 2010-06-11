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

import os
import sys

try:
	from sqlite3 import dbapi2 as sqlite
	from sqlite3 import OperationalError
except ImportError:
	print >>sys.stderr, 'Please install pysqlite2.'
	sys.exit(13)

class database:
	"""
	Interface to the database.
	"""
	def __init__(self, filename):
		"""
		Opens the database, creates tables if necessary.
		"""
		self.filename = filename
		isnew = not os.path.exists(self.filename)
		self.db = sqlite.connect(self.filename, check_same_thread=False)
		self.db.create_function('randomize', 4, self.sqlite_randomize)
		if isnew:
			print >>sys.stderr, 'Initializing ' + self.filename
			cur = self.db.cursor()
			cur.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, priority REAL, name TEXT, repeat INTEGER, delay INTEGER, hours TEXT, days TEXT, last_played INTEGER)')
			cur.execute('CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, playlist TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, artist_weight REAL, weight REAL, count INTEGER, last_played INTEGER)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON tracks (playlist)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
			cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')

	def sqlite_randomize(self, id, artist_weight, weight, count):
		"""
		The randomize() function for SQLite.
		"""
		result = weight or 0
		if artist_weight is not None:
			result = result * artist_weight
		result = result / ((count or 0) + 1)
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

	def update(self, table, args, cur=None):
		if cur is None:
			cur = self.cursor()

		sql = []
		params = []
		for k in args:
			if k != 'id':
				sql.append(k + ' = ?')
				params.append(args[k])
		params.append(args['id'])

		cur.execute('UPDATE %s SET %s WHERE id = ?' % (table, ', '.join(sql)), tuple(params))

def Open(filename):
    return database(filename)
