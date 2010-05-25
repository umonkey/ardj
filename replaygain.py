# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:
#
# replaygain scanner for ardj.
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
ReplayGain scanner for ardj.

Updates RG info in MP3 and OGG/Vorbis files. Reads track peak/gain from
tags, calculates if none (MP3, OGG and FLAC files only). For MP3 files
the ID3v2 (both TXXX and RVA2) and APEv2 tags are read and written.

Usage:

	import replaygain
	replaygain.update(filename)

Command line usage:

	python replaygain.py files...
"""

import os
import subprocess
import sys

import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import RVA2, TXXX
from mutagen.apev2 import APEv2 

def update(filename):
	if not os.access(filename, os.W_OK):
		print >>sys.stderr, 'WARNING: %s is write protected, refusing to update ReplayGain info.' % filename
		return False
	peak, gain = read(filename)
	if peak is not None and gain is not None:
		return write(filename, peak, gain)
	print >>sys.stderr, 'WARNING: no replaygain for %s: peak=%s gain=%s' % (filename, peak, gain)
	return False

def read(filename, update=True):
	"""
	Returns (peak, gain) for a file.
	"""
	peak = gain = None

	def parse_rg(tags):
		p = g = None
		if 'replaygain_track_peak' in tags:
			p = float(tags['replaygain_track_peak'][0])
		if 'replaygain_track_gain' in tags:
			value = tags['replaygain_track_gain'][0]
			if value.endswith(' dB'):
				g = float(value[:-3])
		return (p, g)

	try: peak, gain = parse_rg(mutagen.File(filename, easy=True))
	except: pass

	# Prefer the first value because RVA2 is more precise than
	# APE, formatted as %.2f.
	if peak is None or gain is None:
		try: peak, gain = parse_rg(APEv2(filename))
		except: pass

	if (peak is None or gain is None) and update:
		scanner = None
		ext = os.path.splitext(filename.lower())[1]
		if ext in ('.mp3'):
			scanner = ['mp3gain', '-q', '-s', 'i', filename]
		elif ext in ('.ogg', '.oga'):
			scanner = ['vorbisgain', '-q', '-f', filename]
		elif ext in ('.flac'):
			scanner = ['metaflac', '--add-replay-gain', filename]
		# If the scan is successful, retry reading the tags but only once.
		if scanner is not None and run(scanner):
			return read(filename, update=False)

	return (peak, gain)

def write(filename, peak, gain):
	if peak is None:
		raise Exception('peak is None')
	elif gain is None:
		raise Exception('gain is None')
	try:
		tags = mutagen.File(filename)
		if type(tags) == MP3:
			tags['TXXX:replaygain_track_peak'] = TXXX(encoding=0, desc=u'replaygain_track_peak', text=[u'%.6f' % peak])
			tags['TXXX:replaygain_track_gain'] = TXXX(encoding=0, desc=u'replaygain_track_gain', text=[u'%.2f dB' % gain])
			tags['RVA2:track'] = RVA2(desc=u'track', channel=1, peak=peak, gain=gain)
			tags.save()

			# Additionally write APEv2 tags to MP3 files.
			try: tags = APEv2(filename)
			except: tags = APEv2()
			tags['replaygain_track_peak'] = '%.6f' % peak
			tags['replaygain_track_gain'] = '%.2f dB' % gain
			tags.save(filename)
		else:
			tags['replaygain_track_peak'] = '%.6f' % peak
			tags['replaygain_track_gain'] = '%.2f dB' % gain
			tags.save(filename)
		return True
	except: pass
	return False

def run(args):
	"Runs an external program, returns True on success."
	for path in os.getenv('PATH').split(os.pathsep):
		exe = os.path.join(path, args[0])
		if os.path.exists(exe):
			return subprocess.Popen([exe] + args[1:]).wait() == 0
	return False

def purge(filename):
	try: mutagen.File(filename).delete()
	except: pass
	try: APEv2(filename).delete()
	except: pass

__all__ = ['update']

if __name__ == '__main__':
	import getopt
	import sys

	(opts, args) = getopt.getopt(sys.argv[1:], 'cr')

	f = update
	if ('-c', '') in opts:
		f = purge
	elif ('-r', '') in opts:
		f = read

	if not args:
		print >>sys.stderr, 'Usage: %s [-cr] files...' % sys.argv[0]
		print >>sys.stderr, 'Options:'
		print >>sys.stderr, ' -c    clear all tags (updates by default)'
		print >>sys.stderr, ' -r    read and show tags'
		sys.exit(1)
	for filename in args:
		res = f(filename)
		print '%s: %s' % (filename, res)
