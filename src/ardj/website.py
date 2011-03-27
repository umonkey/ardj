import subprocess
import os

import ardj.settings

def update(task_name=None):
    """Updates the web site.

    Goes to the directory, specified in website/root_dir, and runs make in it.
    If task_name is not specified, it's read from website/make_task, or
    "autoupdate" is used."""
    dirname = ardj.settings.getpath('website/root_dir', '~/.config/ardj/website')
    if os.path.exists(dirname):
        if task_name is None:
            task_name = ardj.settings.get('website/make_task', 'autoupdate')
        subprocess.Popen([ 'make', '-C', dirname, task_name ]).wait()
        return True
    print 'Web site not updated: %s does not exist.' % dirname
    return False
