# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import os

try:
	import yaml
except ImportError:
	print >>sys.stderr, 'Please install PyYAML (python-yaml).'
	sys.exit(13)

class config:
	instance = None

	def __init__(self):
		self.filename = os.path.expandvars('$HOME/.config/ardj/default.yaml')
		self.folder = os.path.dirname(self.filename)
		if not os.path.exists(self.folder):
			os.makedirs(self.folder)
		if not os.path.exists(self.filename):
			raise Exception('Config file %s not found.' % self.filename)
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

	def get_path(self, name):
		return os.path.expandvars(self.get(name))

	def get_db_name(self):
		"""
		Returns the name of the SQLite database.
		"""
		return os.path.splitext(self.filename)[0] + '.sqlite'

	def get_music_dir(self):
		"""
		Returns full path to the music folder.
		"""
		return os.path.realpath(os.path.expandvars(self.get('musicdir', os.path.dirname(self.filename))))

	def get_playlists(self):
		return self.get('playlists')

def get(path, default=None):
	if config.instance is None:
		config.instance = config()
	return config.instance.get(path, default)

def get_path(name):
	return os.path.expandvars(get(name))

def get_self():
	if config.instance is None:
		config.instance = config()
	return config.instance.filename
