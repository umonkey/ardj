# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

try:
	import pyinotify
except ImportError:
	print >>sys.stderr, 'Please install pyinotify.'
	sys.exit(13)

class LogNotifier(pyinotify.ProcessEvent):
	"""
	Tracks changes in a file using inotify.
	"""
	wm = None
	notifier = None

	def __init__(self, cb):
		self.cb = cb
		pyinotify.ProcessEvent.__init__(self)

	def process_IN_MODIFY(self, event):
		self.cb(event)

	@classmethod
	def init(cls, filename, cb):
		cls.wm = pyinotify.WatchManager()
		cls.notifier = pyinotify.ThreadedNotifier(cls.wm, cls(cb))
		cls.wm.add_watch(filename, pyinotify.IN_MODIFY)
		cls.notifier.start()

	@classmethod
	def stop(cls):
		if cls.notifier is not None:
			cls.notifier.stop()
