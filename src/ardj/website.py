import ardj.settings
import subprocess
import os

def update():
    settings = ardj.settings.load('website')
    dirname = settings.getpath('dirname', '~/.config/ardj/website')
    if os.path.exists(dirname):
        subprocess.Popen([ 'make', '-C', dirname, 'update' ]).wait()
        return True
    return False
