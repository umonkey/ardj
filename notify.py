# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:
#
# pyinotify wrapper for ardj.
#
# ardj is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# ardj is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
pyinotify glue for ardj.

This module provides simple functions to use pyinotify for tracking
file changes within a list of paths. This module can also be invoked
from the command line for testing purposes.
"""

import sys

try:
	import pyinotify
except ImportError:
	print >>sys.stderr, 'Please install pyinotify.'
	sys.exit(13)

class Dispatcher(pyinotify.ProcessEvent):
	def __init__(self, callback):
		self.callback = callback
		pyinotify.ProcessEvent.__init__(self)

	def process_default(self, event):
		path = event.pathname
		if event.mask & pyinotify.IN_MOVED_FROM:
			action = 'deleted'
		elif event.mask & pyinotify.IN_MOVED_TO:
			action = 'created'
		elif event.mask & pyinotify.IN_DELETE:
			action = 'deleted'
		elif event.mask & pyinotify.IN_CREATE:
			action = 'created'
		elif event.mask & pyinotify.IN_MODIFY:
			action = 'modified'
		else:
			# unsupported event
			return
		self.callback(action, path)

class Monitor:
	"""
	A monitoring object. Contains references to Watchmanager
	and ThreadedNotifier. Use watch() to start monitoring
	paths, stop() to stop (otherwise the process will become
	a zombie after exit).
	"""
	def __init__(self, callback):
		"""
		Initializes pyinotify objects. Creates a Dispatcher instance,
		which will decode and report events to the callback function.
		"""
		self.wm = pyinotify.WatchManager()
		self.notifier = pyinotify.ThreadedNotifier(self.wm, Dispatcher(callback))

	def __del__(self):
		"""
		This isn't get called during the example below, but just in case.
		"""
		self.stop()

	def watch(self, paths):
		"""
		Starts watching for paths. Tracks file changes.
		"""
		for path in paths:
			# For more codes see:
			# http://pyinotify.sourceforge.net/#The_EventsCodes_Class
			self.wm.add_watch(path, pyinotify.IN_MODIFY|pyinotify.IN_CREATE|pyinotify.IN_DELETE|pyinotify.IN_MOVED_FROM|pyinotify.IN_MOVED_TO, rec=True, auto_add=True)
		self.notifier.start()
		return self

	def stop(self):
		"""
		Stop watching for files. Shuts down pyinotify threds. Without calling
		this function threads remain active even after you call sys.exit(),
		turning the process into a zombie.
		"""
		if self.notifier is not None:
			self.notifier.stop()
			self.notifier = None
		return self

def monitor(paths, callback):
	"""
	Creates and initializes a Monitor. The returned objec is only
	useful for calling stop() when you no longer need to monitor
	the paths.
	"""
	return Monitor(callback).watch(paths)

if __name__ == '__main__':
	"""
	This is a usage example and a test case, all in one.
	"""
	import os
	import time # to sleep waiting for an interrupt

	def callback(action, path):
		print 'callback: action=%s path=%s' % (action, path)

	if len(sys.argv) < 2:
		print >>sys.stderr, 'Usage: %s paths...' % os.path.basename(sys.argv[0])
		sys.exit(1)

	m = monitor(sys.argv[1:], callback)
	print 'Waiting for an interrupt (Ctrl+C).'

	try:
		while True:
			time.sleep(1)
	except KeyboardInterrupt:
		print 'Shutting down.'
		# Without this the process will zombify on exit.
		m.stop()
