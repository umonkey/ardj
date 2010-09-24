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
		cur = self.db.cursor()
		cur.execute('CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, priority REAL, name TEXT, repeat INTEGER, delay INTEGER, hours TEXT, days TEXT, last_played INTEGER)')
		cur.execute('CREATE TABLE IF NOT EXISTS tracks (id INTEGER PRIMARY KEY, playlist TEXT, filename TEXT, artist TEXT, title TEXT, length INTEGER, artist_weight REAL, weight REAL, count INTEGER, last_played INTEGER)')
		cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON tracks (playlist)')
		cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_last ON tracks (last_played)')
		cur.execute('CREATE INDEX IF NOT EXISTS idx_tracks_count ON tracks (count)')
		cur.execute('CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY, track_id INTEGER, owner TEXT)')
		# голоса пользователей
		cur.execute('CREATE TABLE IF NOT EXISTS votes (track_id INTEGER NOT NULL, email TEXT NOT NULL, vote INTEGER, weight REAL)')
		cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_track_id ON votes (track_id)')
		cur.execute('CREATE INDEX IF NOT EXISTS idx_votes_email ON votes (email)')
		# карма
		cur.execute('CREATE TABLE IF NOT EXISTS karma (email TEXT, weight REAL)')
		cur.execute('CREATE INDEX IF NOT EXISTS idx_karma_email ON karma (email)')
		# View для подсчёта веса дорожек на основании кармы.
		# weight = max(0.1, 1 + sum(vote * weight))
		cur.execute('CREATE VIEW IF NOT EXISTS track_weights AS SELECT v.track_id AS track_id, COUNT(*) AS count, MAX(0.1, 1 + SUM(v.vote * k.weight)) AS weight FROM votes v INNER JOIN karma k ON k.email = v.email GROUP BY v.track_id')

	def __del__(self):
		self.commit()
		print >>sys.stderr, 'Database closed.'

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

	def add_vote(self, track_id, email, vote):
		"""Adds a vote for/against a track, returns track's current weight.

		The process is: 1) add a record to the votes table, 2) update email's
		record in the karma table, 3) update weight for all tracks email voted
		for/against.

		Votes other than +1 and -1 are skipped.
		"""
		cur = self.cursor()

		# Normalize the vote.
		if vote > 0: vote = 1
		elif vote < 0: vote = -1

		# Skip wrong values.
		if vote != 0:
			cur.execute('DELETE FROM votes WHERE track_id = ? AND email = ?', (track_id, email, ))
			cur.execute('INSERT INTO votes (track_id, email, vote) VALUES (?, ?, ?)', (track_id, email, vote, ))

		# Update email's karma.
		all = float(cur.execute('SELECT COUNT(*) FROM votes').fetchall()[0][0])
		his = float(cur.execute('SELECT COUNT(*) FROM votes WHERE email = ?', (email, )).fetchall()[0][0])
		cur.execute('DELETE FROM karma WHERE email = ?', (email, ))
		cur.execute('INSERT INTO karma (email, weight) VALUES (?, ?)', (email, his / all, ))

		# Update all track weights.  Later this can be replaced with joins and
		# views (when out of beta).
		cur.execute('UPDATE tracks SET weight = 1')
		result = 1
		for row in cur.execute('SELECT track_id, weight FROM track_weights WHERE track_id IN (SELECT track_id FROM votes WHERE email = ?)', (email, )).fetchall():
			cur.execute('UPDATE tracks SET weight = ? WHERE id = ?', (row[1], row[0], ))
			if track_id == row[0]:
				result = row[1]

		self.commit()
		return result

def Open(filename):
    return database(filename)
