# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import logging
import os
import sys
import time

try:
	import yaml
except ImportError:
	logging.critical(u'Please install PyYAML (python-yaml).')
	sys.exit(13)

class config:
	def __init__(self):
		self.config_filename = None
		self.config_mtime = None
		self.config_data = {}
		self.playlists_mtime = None
		self.playlists_data = []

		for filename in [os.path.expandvars('$HOME/.config/ardj/default.yaml'), '/etc/ardj.yaml']:
			if os.path.exists(filename):
				self.config_filename = filename
				break
		if not self.config_filename:
			raise Exception('Could not find a config file.')
		self.folder = os.path.dirname(self.config_filename)
		if not os.path.exists(self.folder):
			os.makedirs(self.folder)

	def __del__(self):
		self.close()

	def load(self):
		"""
		Reloads the file if it was changed or never loaded.
		"""
		stat = os.stat(self.config_filename)
		if self.config_mtime is None or self.config_mtime < stat.st_mtime:
			self.config_mtime = stat.st_mtime
			self.config_data = yaml.load(open(self.config_filename, 'r').read())
			logging.info(u'Read %s' % self.config_filename)

	def close(self):
		pass

	def get(self, path, default=None, fail=False):
		"""
		Returns the value of a config parameter. Path is of the x/y/z form.
		If there is no such value, default is returned.
		"""
		self.load()
		data = self.config_data
		for k in path.split('/'):
			if not k in data:
				if default is None and fail:
					raise Exception('Error: the %s parameter is not set.' % path)
				return default
			data = data[k]
		return data

	def get_path(self, name, default=None):
		return os.path.expandvars(self.get(name, default))

	def get_db_name(self):
		"""
		Returns the name of the SQLite database.
		"""
		return self.get_path('database', os.path.splitext(self.config_filename)[0] + '.sqlite')

	def get_music_dir(self):
		"""
		Returns full path to the music folder.
		"""
		return os.path.realpath(os.path.expandvars(self.get('musicdir', os.path.dirname(self.config_filename))))

	def get_playlists(self):
		filename = os.path.join(self.get_music_dir(), 'playlists.yaml')
		if not os.path.exists(filename):
			logging.warning(u'%s does not exist, assuming empty.' % filename)
			return []
		stat = os.stat(filename)
		if self.playlists_mtime is None or self.playlists_mtime < stat.st_mtime:
			self.playlists_mtime = stat.st_mtime
			self.playlists_data = yaml.load(open(filename, 'r').read())
		return self.playlists_data

def Open():
	return config()
