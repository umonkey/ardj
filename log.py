import sys
import time
import traceback

def log(message, trace=False):
    if type(message) == unicode:
        message = message.encode('utf-8')
    prefix = time.strftime('%Y-%m-%d %H:%M:%S ', time.localtime())
    message = message.strip()
    if trace:
        message += '\n' + traceback.format_exc().strip()
    for line in message.split('\n'):
        if '--quiet' not in sys.argv:
            print >>sys.stderr, prefix + line
