# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import logging
import os
import sys

import notify

try:
	import yaml
except ImportError:
	logging.critical(u'Please install PyYAML (python-yaml).')
	sys.exit(13)

class config:
	def __init__(self):
		self.filename = None
		for filename in [os.path.expandvars('$HOME/.config/ardj/default.yaml'), '/etc/ardj.yaml']:
			if os.path.exists(filename):
				self.filename = filename
				break
		if not self.filename:
			raise Exception('Could not find a config file.')
		self.reload = False
		self.tracker = None
		self.folder = os.path.dirname(self.filename)
		if not os.path.exists(self.folder):
			os.makedirs(self.folder)
		self.load()

	def __del__(self):
		self.close()

	def close(self):
		if self.tracker:
			self.tracker.stop()
			self.tracker = None

	def start_tracking(self):
		if self.tracker is None:
			self.tracker = notify.monitor([self.filename], self.on_file_changed)

	def load(self):
		self.data = yaml.load(open(self.filename, 'r').read())
		self.reload = False

	def on_file_changed(self, action, path):
		"""
		Called by the notify module when the file is changed.
		"""
		self.reload = True

	def get(self, path, default=None):
		"""
		Returns the value of a config parameter. Path is of the x/y/z form.
		If there is no such value, default is returned.
		"""
		if self.reload:
			logging.info(u'Reloading ' + self.filename)
			self.load()
		data = self.data
		for k in path.split('/'):
			if not k in data:
				return default
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
			logging.warning(u'%s does not exist, assuming empty.' % filename)
			return []
		return yaml.load(open(filename, 'r').read())

def Open():
	return config()
