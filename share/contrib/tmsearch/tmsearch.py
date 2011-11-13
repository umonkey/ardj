#!/usr/bin/python
# -*- coding: utf-8 -*-

import time, os, sys
import web, re
import os.path

from datetime import datetime
from tmthink import TmThinker
from render import render_to_response

def log(text, logFileHandler = False):
    text=text.encode('utf-8')
    needToClose = False
    if not logFileHandler:
        logFileHandler=open(LOGDIR+"tmsearch.log","a")
        needToClose = True
    if logFile: logFileHandler.write(text)
    print text
    if needToClose: logFileHandler.close()


class main:
    def GET(self):
        args = web.input()
        return "Hello, world! %)"+args.get("some", "no")

urls = ('/', 'main',
        '/tm','TmThinker',
        '/tm/(.*)','TmThinker',
        )
if __name__ == "__main__":
    cache = False
    t_globals = dict(datestr=web.datestr,)
    render = web.template.render('', cache=cache, globals=t_globals)
    render._keywords['globals']['render'] = render
    app = web.application(urls, globals())
    print "app.run()"
    app.run()

