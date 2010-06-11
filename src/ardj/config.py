# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os
import sys

try:
	import yaml
except ImportError:
	print >>sys.stderr, 'Please install PyYAML (python-yaml).'
	sys.exit(13)

class config:
	def __init__(self):
		for filename in [os.path.expandvars('$HOME/.config/ardj/default.yaml'), '/etc/ardj.yaml']:
			if os.path.exists(filename):
				self.filename = filename
				break
		if not self.filename:
			raise Exception('Could not find a config file.')
		self.folder = os.path.dirname(self.filename)
		if not os.path.exists(self.folder):
			os.makedirs(self.folder)
		self.data = yaml.load(open(self.filename, 'r').read())

	def get(self, path, default=None):
		"""
		Returns the value of a config parameter. Path is of the x/y/z form.
		If there is no such value, default is returned.
		"""
		data = self.data
		for k in path.split('/'):
			if not k in data:
				if default is not None:
					return default
				raise Exception('%s does not define %s' % (self.filename, path))
			data = data[k]
		return data

	def get_path(self, name, default=None):
		return os.path.expandvars(self.get(name, default))

	def get_db_name(self):
		"""
		Returns the name of the SQLite database.
		"""
		return self.get_path('database', os.path.splitext(self.filename)[0] + '.sqlite')

	def get_music_dir(self):
		"""
		Returns full path to the music folder.
		"""
		return os.path.realpath(os.path.expandvars(self.get('musicdir', os.path.dirname(self.filename))))

	def get_playlists(self):
		filename = os.path.join(self.get_music_dir(), 'playlists.yaml')
		if not os.path.exists(filename):
			print >>sys.stderr, '%s does not exist, assuming empty.' % filename
			return []
		return yaml.load(open(filename, 'r').read())

def Open():
	return config()
