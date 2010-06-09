import sys
from ardj import Open

songnumber = -1
ardj = None

# Function called to initialize your python environment.
# Should return 1 if ok, and 0 if something went wrong.
def ices_init ():
    global ardj
	print 'ardj: initializing.'
    ardj = Open()
	return 1

# Function called to shutdown your python enviroment.
# Return 1 if ok, 0 if something went wrong.
def ices_shutdown ():
    global ardj
	print 'ardj: shutting down.'
    ardj.close()
	return 1

# Function called to get the next filename to stream. 
# Should return a string.
def ices_get_next ():
	print 'ardj: requesting next track.'
	return '/radio/04 Outcast.mp3'

# This function, if defined, returns the string you'd like used
# as metadata (ie for title streaming) for the current song. You may
# return null to indicate that the file comment should be used.
def ices_get_metadata ():
        print 'ardj: returning metadata.'
        return '"Outcast" by Mike Oldfield'

# Function used to put the current line number of
# the playlist in the cue file. If you don't care about this number
# don't use it.
def ices_get_lineno ():
	global songnumber
	print 'ardj: returning line number.'
	songnumber = songnumber + 1
	return songnumber
