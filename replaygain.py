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

Updates RG info in MP3 and OGG/Vorbis files. Command line usage:

python replaygain.py files...
"""

import os
import subprocess

import mutagen
from mutagen.mp3 import MP3
from mutagen.apev2 import APEv2 

def update(filename):
	if not os.access(filename, os.W_OK):
		return False
	ext = os.path.splitext(filename.lower())[1]
	if ext == '.mp3':
		return update_mp3(filename)
	elif ext == '.ogg':
		return update_ogg(filename)
	return False

def update_ogg(filename):
	tags = mutagen.File(filename)
	if 'replaygain_track_peak' not in tags or 'replaygain_track_gain' not in tags:
		return run(['vorbisgain', '-q', '-f', filename])
	return True

def update_mp3(filename):
	return update_mp3_id3(filename) and update_mp3_ape(filename)

def update_mp3_id3(filename):
	"""
	Updates ID3v2 tags if necessary. Uses mp3gain to calculate the values.
	"""
	tags = mutagen.File(filename)
	if 'TXXX:replaygain_track_gain' in tags and 'TXXX:replaygain_track_peak' in tags:
		return True
	return run(['mp3gain', '-q', filename])

def update_mp3_ape(filename):
	"""
	Copies ID3v2 tags to APE.
	"""
	id3 = mutagen.File(filename)
	ape = APEv2(filename)
	peak = gain = update = 0
	if 'TXXX:replaygain_track_peak' in id3 and 'replaygain_track_peak' not in ape:
		try:
			peak = float(tags['TXXX:replaygain_track_peak'].text[0])
			update = True
		except: pass
	if 'TXXX:replaygain_track_gain' in id3 and 'replaygain_track_gain' not in ape:
		try:
			gain = float(tags['TXXX:replaygain_track_gain'].text[0][:-3])
			update = True
		except: pass
	if update:
		ape['replaygain_track_peak'] = '%.6f' % peak
		ape['replaygain_track_gain'] = '%.2f dB' % gain
		ape.save()
		return True
	return False

def run(args):
	for path in os.getenv('PATH').split(os.pathsep):
		exe = os.path.join(path, args[0])
		if os.path.exists(exe):
			args[0] = exe
			if subprocess.Popen(args).wait():
				return True
	return False

def purge(filename):
	try:
		tags = mutagen.File(filename)
		tags.delete()
	except: pass
	try:
		tags = APEv2(filename)
		tags.delete()
	except: pass

__all__ = ['update']

if __name__ == '__main__':
	import getopt
	import sys

	(opts, args) = getopt.getopt(sys.argv[1:], 'c')

	f = update
	if ('-c', '') in opts:
		f = purge

	if not args:
		print >>sys.stderr, 'Usage: %s files...' % sys.argv[0]
		sys.exit(1)
	for filename in args:
		res = f(filename)
		print '%s: %s' % (filename, res)
