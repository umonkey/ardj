import os
import sys

import ardj.log
import ardj.tracks

songnumber = -1
last_track = None

def ices_init():
	"""
	Function called to initialize your python environment.
	Should return 1 if ok, and 0 if something went wrong.
	"""
	global ardj
	ardj.log.info('ices/ardj: initializing.')
	return 1

def ices_shutdown():
	"""
	Function called to shutdown your python enviroment.
	Return 1 if ok, 0 if something went wrong.
	"""
	global ardj
	if ardj:
		ardj.log.info('ices/ardj: shutting down.')
	return 1

def ices_get_next():
	"""
	Function called to get the next filename to stream. 
	Should return a string.
	"""
	global ardj, last_track
	if not ardj: ices_init()
	# print >>sys.stderr, 'ices/ardj: requesting next track.'
    track_id = ardj.track.get_next_track_id()
    if track_id:
        last_track = ardj.track.get_track_by_id(track_id)
	return last_track['filepath']

def ices_get_metadata():
	"""
	This function, if defined, returns the string you'd like used
	as metadata (ie for title streaming) for the current song. You may
	return null to indicate that the file comment should be used.
	"""
	global last_track
	# print >>sys.stderr, 'ices/ardj: returning metadata.'
	if last_track:
		if last_track.has_key('artist') and last_track.has_key('title'):
			return ('"%s" by %s' % (last_track['title'], last_track['artist'])).encode('utf-8')
		return os.path.basename(last_track['filepath'])
	return 'Unknown track'

def ices_get_lineno():
	"""
	Function used to put the current line number of
	the playlist in the cue file. If you don't care about this number
	don't use it.
	"""
	global songnumber
	# print >>sys.stderr, 'ices/ardj: returning line number.'
	songnumber = songnumber + 1
	return songnumber
