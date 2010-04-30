import sys
import time

def log(message):
    if type(message) == unicode:
        message = message.encode('utf-8')
    message = time.strftime('%Y-%m-%d %H:%M:%S ', time.localtime()) + message.strip()
    print >>sys.stderr, message
