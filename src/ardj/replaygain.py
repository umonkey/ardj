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

import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import RVA2, TXXX
from mutagen.apev2 import APEv2 

import ardj.database
import ardj.log
import ardj.util

def update(filename):
	"""Updates RG if necessary."""
	if check(filename):
		return True

	peak, gain = read(filename)
	if peak is not None and gain is not None:
		return write(filename, peak, gain)
	ardj.log.warning('No replaygain for %s: peak=%s gain=%s' % (filename, peak, gain))
	return False

def check(filename):
	"""Returns True if the file has all ReplayGain data."""
	try:
		tags = mutagen.File(filename)

		if type(tags) != MP3:
			return 'replaygain_track_peak' in tags and 'replaygain_track_gain' in tags
		if 'TXXX:replaygain_track_peak' not in tags or 'TXXX:replaygain_track_gain' not in tags:
			return False
		if 'RVA2:track' not in tags:
			return False
		tags = APEv2(filename)
		return 'replaygain_track_peak' in tags and 'replaygain_track_gain' in tags
	except:
		return False

def read(filename, update=True):
	"""Returns (peak, gain) for a file."""
	peak = gain = None

	def parse_rg(tags):
		p = g = None
		if 'replaygain_track_peak' in tags:
			p = float(tags['replaygain_track_peak'][0])
		if 'replaygain_track_gain' in tags:
			value = tags['replaygain_track_gain'][0]
			if value.endswith(' dB'):
				g = float(value[:-3])
			else:
				ardj.log.warning('Malformed track gain info: "%s" in %s' % (value, filename))
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
		if scanner is not None and ardj.util.run(scanner, quiet=True):
			peak, gain = read(filename, update=False)

	return (peak, gain)

def write(filename, peak, gain):
	"""Writes RG tags to file."""
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

def purge(filename):
	"""Removes known tags from the specified file."""
	try: mutagen.File(filename).delete()
	except: pass
	try: APEv2(filename).delete()
	except: pass

USAGE = """Usage: ardj rg all|filenames..."""

def run_cli(args):
	"""Implements the "ardj rg" command."""
	if not len(args):
		print USAGE
		return

	if args == ['all']:
		musicdir = ardj.settings.getpath('musicdir')
		if not musicdir:
			raise Exception('musicdir not set.')
		elif not os.path.exists(musicdir):
			raise Exception('Directory %s does not exist.' % musicdir)
		cur = ardj.database.Open().cursor()
		cur.execute('SELECT filename FROM tracks')
		args = [os.path.join(musicdir, row[0]) for row in cur.fetchall()]

	if args:
		for filename in args:
			update(filename)
