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
	print " -d           run a jabber bot"
	print " -n           show next track"
	print " -N NUM       show NUM next tracks"
	print " -u           update database"
	return 1

if __name__ == '__main__':
	try:
		opts, args = getopt.getopt(sys.argv[1:], 'cdnN:u')
	except getopt.GetoptError:
		sys.exit(usage())

	if not len(opts):
		sys.exit(usage())

	for option, value in opts:
		if '-c' == option:
			for dir in os.getenv('PATH').split(os.pathsep):
				cmd = os.path.join(dir, 'sqlite3')
				if os.path.exists(cmd):
					import ardj.db
					os.execv(cmd, ['-header', ardj.db.db().filename])
			print 'Could not find sqlite3 binary.'
		if '-d' == option:
			import ardj.jabber
			ardj.jabber.run()
		if '-n' == option:
			import ardj.db
			db = ardj.db.db()
			track = db.get_random_track()
			if track is None:
				print >>sys.stderr, 'Could not find a track to play.'
				sys.exit(1)
			print track['filepath'].encode('utf-8')
			db.commit()
		if '-N' == option:
			import ardj.db
			db = ardj.db.db()
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
		if '-u' == option:
			import ardj.db
			ardj.db.db().update_files()
