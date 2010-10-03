# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import re
import sys
import time

try:
	import lastfm.client
	have_cli = True
except ImportError:
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
		self.skip_files = None
		self.skip_labels = self.config.get('lastfm/skip_labels', [])
		self.folder = self.config.get_music_dir()
		if have_cli:
			self.cli = lastfm.client.Daemon('ardj')
			self.cli.open_log()
		else:
			print >>sys.stderr, 'Scrobbler disabled: please install lastfmsubmitd.'
			self.cli = None
		skip = self.config.get('lastfm/skip_files', '')
		if skip:
			self.skip_files = re.compile(skip)

	def submit(self, track):
		"""
		Reports a track, which must be a dictionary containing keys: file,
		artist, title. If a key is not there, the track is not reported.
		"""
		if self.cli is not None:
			try:
				if self.__skip_filename(track):
					pass
				elif self.__skip_labels(track):
					pass
				elif track['artist'] and track['title']:
					data = { 'artist': track['artist'].strip(), 'title': track['title'].strip(), 'time': time.gmtime(), 'length': track['length'] }
					self.cli.submit(data)
					print >>sys.stderr, 'scrobbler: sent "%s" by %s' % (data['title'].encode('utf-8'), data['artist'].encode('utf-8'))
				else:
					print >>sys.stderr, 'scrobbler: no tags in %s' % track['filename'].encode('utf-8')
			except KeyError, e:
				print >>sys.stderr, (u'scrobbler: no %s in %s' % (e.args[0], track)).encode('utf-8')

	def __skip_filename(self, track):
		"""
		Returns True if the track has a forbidden filename.
		"""
		if self.skip_files is None:
			return False
		if self.skip_files.match(track['filename']):
			print >>sys.stderr, u'scrobbler: skipped %s (forbidden file name)' % track['filename']
			return True
		return False

	def __skip_labels(self, track):
		"""
		Returns True if the track has a label which forbids scrobbling.
		"""
		if not self.skip_labels:
			return False
		if not track.has_key('labels'):
			return False
		for label in self.skip_labels:
			if label in track['labels']:
				print >>sys.stderr, 'scrobbler: skipped %s (forbidden label: %s)' % (track['filename'], label)
				return True
		return False

def Open(config):
	if not config.get('lastfm/enable', False):
		return None
	if not have_cli:
		print >>sys.stderr, 'Last.fm scrobbler is not available: please install lastfmsubmitd.'
		return None
	return client(config)
