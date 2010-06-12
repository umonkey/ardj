# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import re
import sys
import time

try:
	import lastfm.client
	have_cli = True
except ImportError:
	print >>sys.stderr, 'scrobbler: disabled, please install lastfmsubmitd.'
	have_cli = False

class client:
	"""
	Last.fm client class. Uses lastfmsubmitd to send track info. Uses config
	file parameter lastfm/skip as a regular expression to match files that
	must never be reported (such as jingles).
	"""
	def __init__(self, config):
		"""
		Imports and initializes lastfm.client, reads options from bot's config file.
		"""
		self.config = config
		self.skip = None
		self.folder = self.config.get_music_dir()
		if have_cli:
			self.cli = lastfm.client.Daemon('ardj')
			self.cli.open_log()
		else:
			print >>sys.stderr, 'Scrobbler disabled: please install lastfmsubmitd.'
			self.cli = None
		self.skip = None
		skip = self.config.get('lastfm/skip', '')
		if skip:
			self.skip = re.compile(skip)

	def submit(self, track):
		"""
		Reports a track, which must be a dictionary containing keys: file,
		artist, title. If a key is not there, the track is not reported.
		"""
		if self.cli is not None:
			try:
				if self.skip is not None and self.skip.match(track['filename']):
					print >>sys.stderr, 'scrobbler: skipped %s' % track['filename']
				elif track['artist'] and track['title']:
					data = { 'artist': track['artist'], 'title': track['title'], 'time': time.gmtime(), 'length': track['length'] }
					self.cli.submit(data)
					print >>sys.stderr, 'scrobbler: sent "%s" by %s' % (track['title'].encode('utf-8'), track['artist'].encode('utf-8'))
				else:
					print >>sys.stderr, 'scrobbler: no tags in %s' % track['filename'].encode('utf-8')
			except KeyError, e:
				print >>sys.stderr, (u'scrobbler: no %s in %s' % (e.args[0], track)).encode('utf-8')

def Open(config):
	return have_cli and client(config)
