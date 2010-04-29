# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

# System imports.
import lastfm
import re

# Local imports.
import config

class client:
	"""
	Last.fm client class. Uses lastfmsubmitd to send track info. Uses config
	file parameter lastfm/skip as a regular expression to match files that
	must never be reported (such as jingles).
	"""
	def __init__(self):
		"""
		Imports and initializes lastfm.client, reads options from bot's config file.
		"""
		self.config = config.config()
		self.skip = None
		self.folder = self.config.get_music_dir()
		try:
			import lastfm.client
			self.cli = lastfm.client.Daemon('ardj')
			self.cli.open_log()
		except ImportError:
			print >>sys.stderr, 'Last.fm disabled: please install lastfmsubmitd.'
			self.cli = None
		self.skip = None
		skip = self.config.get('lastfm/skip', '')
		if skip:
			re.compile(skip)

	def submit(self, track):
		"""
		Reports a track, which must be a dictionary containing keys: file,
		artist, title. If a key is not there, the track is not reported.
		"""
		if self.cli is not None:
			try:
				if self.skip is not None and self.skip.match(track['file']):
					print 'Last.fm: skipped', track['file']
				else:
					filename = os.path.join(self.folder, track['file'])
					self.cli.submit({ 'artist': track['artist'], 'title': track['title'], 'time': time.gmtime(), 'length': mutagen.File(filename).info.length })
			except KeyError, e:
				print >>sys.stderr, 'Last.fm: no %s in %s' % (e.args[0], track)
