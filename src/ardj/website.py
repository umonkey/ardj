import ardj.settings
import subprocess
import os

def update(task_name='autoupdate'):
    settings = ardj.settings.load('website')
    dirname = settings.getpath('root_dir', '~/.config/ardj/website')
    if os.path.exists(dirname):
        subprocess.Popen([ 'make', '-C', dirname, task_name ]).wait()
        return True
    return False
