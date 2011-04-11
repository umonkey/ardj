# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import logging
import sys

try:
	import mutagen as mutagen
	import mutagen.mp3 as mp3
	import mutagen.easyid3 as easyid3
	from mutagen.apev2 import APEv2 
	easyid3.EasyID3.RegisterTXXXKey('ardj', 'ardj metadata')
except ImportError, e:
	logging.critical('Pleasy install python-mutagen (%s)' % e)
	sys.exit(13)

def raw(filename):
	"""
	Returns a mutagen object that corresponds to filename. The object can be
	used as a dictionary to access lists of tags, e.g.: t['title'][0]. Track
	length in seconds is t.info.length.
	"""
	try:
		if filename.lower().endswith('.mp3'):
			t = easyid3.Open(filename)
			return t
		return mutagen.File(filename)
	except Exception, e:
		logging.error('No tags in %s: %s' % (filename, e))
		return None

def get(filename):
	result = {}
	t = raw(filename)
	if t is None:
		return None
	for k in ('artist', 'title', 'album', 'ardj'):
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

def set(filename, tags):
	try:
		t = raw(filename)
		for k in tags:
			try:
				if tags[k]: t[k] = tags[k]
			except Exception, e:
				logging.error(u'Could not write tags to %s: %s' % (filename, e))
		t.save()
	except Exception, e:
		logging.error(u'Could not save tags to %s: %s' % (filename, e), trace=True)

__all__ = ['get', 'set']
