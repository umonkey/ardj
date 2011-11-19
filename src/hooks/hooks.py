"""Mercurial hooks for ardj.

These hooks will help you keep the source code working.  They are installed
with the `make install-hooks' command.
"""

import re
import subprocess
import sys


def check_commit_message(repo, *args, **kwargs):
    message = repo["tip"].description()

    if not re.search("issue \d+", message, re.I):
        print >> sys.stderr, "You MUST refer to an issue, e.g.: Fixes issue 123."
        return True

    print >> sys.stderr, "Running other hooks."
    subprocess.Popen(["make", "pre-commit"]).wait()
