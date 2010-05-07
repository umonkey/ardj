#!/usr/bin/env python
# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import getopt
import os
import sys
import traceback

def usage():
	print "Usage: %s [options]" % os.path.basename(sys.argv[0])
	print "\nBasic options:"
	print " -c           open SQLite console"
	print " -d           run a jabber bot (consider using `./monitor ardj -d')"
	print " -i FILES     add FILES to the database"
	print " -n           show next track"
	print " -N NUM       show NUM next tracks (debug, no DB updates)"
	print " -R           reset database"
	print " -s           scrobble track (only with -n)"
	print " -S           show database statistics"
	print " -u           update database"
	return 1

if __name__ == '__main__':
	try:
		opts, args = getopt.getopt(sys.argv[1:], 'cdinN:RsSu')
	except getopt.GetoptError:
		sys.exit(usage())

	if not len(opts):
		sys.exit(usage())

	for option, value in opts:
		if '-c' == option:
			for dir in os.getenv('PATH').split(os.pathsep):
				cmd = os.path.join(dir, 'sqlite3')
				if os.path.exists(cmd):
					from lib.db import db
					os.execv(cmd, ['-header', db().filename])
			print 'Could not find sqlite3 binary.'
		if '-d' == option:
			from lib.jabber import run
			run()
		if '-i' == option:
			if not len(args):
				sys.exit(usage())
			import lib.db as db
			for arg in args:
				t = db.track.add(arg)
				print arg, t
		if '-n' == option:
			import lib.db
			track = lib.db.track.get_random()
			if track is None:
				print >>sys.stderr, 'Could not find a track to play.'
				sys.exit(1)
			if ('-s', '') in opts:
				track.scrobble()
			print track['filepath'].encode('utf-8')
			db.commit()
		if '-N' == option:
			import lib.db
			db = lib.db.db()
			limit = int(value)
			while limit:
				track = db.get_random_track()
				if track is None:
					print >>sys.stderr, 'Could not find a track to play.'
					sys.exit(1)
				# print track # ['path']
				print u'%05u %s/%s' % (track['id'], track['playlist'], track['filename'])
				limit = limit - 1
			db.rollback()
		if '-R' == option:
			import lib.config
			filename = lib.config.config().get_db_name()
			if os.path.exists(filename):
				os.unlink(filename)
				print 'OK'
		if '-S' == option:
			import lib.db
			count, length = lib.db.db().get_stats()
			print '%u tracks, %.1f hours.' % (count, length / 60 / 60)
		if '-u' == option:
			from lib.db import db
			db().update_files()
