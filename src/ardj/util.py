import os
import subprocess
import tempfile

def run(command):
    command = [str(x) for x in command]
    print '> ' + ' '.join(command)
    subprocess.Popen(command).wait()
    return True

class mktemp:
    def __init__(self, suffix=''):
        self.filename = tempfile.mkstemp(prefix='ardj_', suffix=suffix)[1]
        os.chmod(self.filename, 0664)

    def __del__(self):
        if os.path.exists(self.filename):
            print 'Deleting temporary file %s' % self.filename
            os.unlink(self.filename)

    def __str__(self):
        return self.filename

    def __unicode__(self):
        return unicode(self.filename)
