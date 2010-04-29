# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import sys

try:
	import mutagen
	import mutagen.easyid3
except ImportError:
	print >>sys.stderr, 'Pleasy install python-mutagen.'
	sys.exit(13)

def raw(filename):
	"""
	Returns a mutagen object that corresponds to filename. The object can be
	used as a dictionary to access lists of tags, e.g.: t['title'][0]. Track
	length in seconds is t.info.length.
	"""
	try:
		if filename.lower().endswith('.mp3'):
			return mutagen.easyid3.Open(filename)
		return mutagen.File(filename)
	except Exception, e:
		print >>sys.stderr, 'No tags for %s: %s' % (filename, e)
		return None

def get(filename):
	result = {}
	t = raw(filename)
	if t is None:
		return None
	for k in ('artist', 'title', 'album'):
		if k in t:
			result[k] = t[k][0]
		else:
			result[k] = None
	if hasattr(t, 'info'):
		result['length'] = t.info.length
	else:
		t = mutagen.File(filename)
		result['length'] = t.info.length
	return result
