import os
import sys

import ardj.settings
import ardj.util

def sox(args, suffix='.wav'):
    output_fn = ardj.util.mktemp(suffix=suffix)
    args = [(arg == 'OUTPUT') and output_fn or arg for arg in args]
    ardj.util.run(['sox'] + args)
    return output_fn

def mkpodcast(source):
    """Cleans up a live dump, creates a podcast.
    
    Source is the name of the dump file created by icecast.  Returns a
    temporary MP3 file name which must be moved somewhere else or deleted."""
    noise_profile = ardj.settings.getpath('postproduction/noise_profile')
    if not os.path.exists(noise_profile):
        print >>sys.stderr, 'WARNING: postproduction/noise_profile not set.'
    else:
        noise_strength = str(ardj.settings.get('postproduction/noise_strength', '0.3'))
        source = sox([ source, 'OUTPUT', 'noisered', noise_profile, noise_strength, 'silence', '-l', '1', '0.2', '-50d', '-1', '0.2', '-50d', 'norm' ])

    output = ardj.util.mktemp(suffix='.mp3')
    ardj.util.run([ 'lame', '-m', 'm', '-B', '64', '--resample', '44100', source, output ])
    ardj.util.run([ 'mp3gain', output ])
