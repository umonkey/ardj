import sys
import time

def log(message):
    message = time.strftime('%Y-%m-%d %H:%M:%S ', time.localtime()) + message.strip()
    print >>sys.stderr, message
