#!/usr/bin/env python
# encoding=utf-8

"""RSS to chat translator.

Picks the latest unseen entry from a news feed and sends it to the chat room
using the "ardj xmpp-send" command.  Designed to be run hourly using a cron job
like this:

    0 7-23 * * * python ~/src/ardj/share/contrib/newswire/newswire.py

By default reads top 10 news from newsru.com; a different feed URL can be
passed as the first command line argument, e.g.:

    python newswire.py http://example.com/rss.xml

If you want to do something else with the news (e.g., send to Twitter), edit
the COMMAND constant.
"""

import os
import random
import re
import subprocess
import sys
import time
import urllib

import feedparser


HISTFILE = "~/.newswire"
HISTSIZE = 100
COMMAND = "ardj xmpp-send"

FUNNY_PATTERN = u"жирин|зюганов|путин|медведев|нургалиев|онищенко|блог|дума|президент|дипломат|губернатор"

def is_funny(text):
    return re.search(FUNNY_PATTERN, text, re.I|re.U) is not None


def run(command):
    p = subprocess.PIPE
    pp = subprocess.Popen(command, stdout=p, stderr=p)
    out, err = pp.communicate()
    return out, err, pp.returncode


def read_history():
    """Returns URLS that already were published."""
    fn = os.path.expanduser(HISTFILE)
    if not os.path.exists(fn):
        return []
    return file(fn, "rb").read().decode("utf-8").strip().split("\n")


def write_history(urls):
    """Writes URLs to the history file."""
    fn = os.path.expanduser(HISTFILE)
    data = u"\n".join(urls[-HISTSIZE:])
    file(fn, "wb").write(data.encode("utf-8"))


def fetch_news(feed_url):
    """Returns (url, description) pairs for the specified feed."""
    feed = feedparser.parse(feed_url)
    return [(e["link"], e["title"]) for e in feed["entries"]]


def short_url(url):
    """Returns the URL shortened with clck.ru"""
    try:
        req = urllib.urlopen("http://clck.ru/--?url=" + url)
        if req.getcode() == 200:
            return req.read()
    except:
        pass
    return url


def send_news(url, text):
    """Sends the news to the chat room."""
    message = u"%s: %s" % (text, short_url(url))
    if is_funny(text):
        message += u" %s" % random.choice([":D", ";)", "o_O", ":("])
    command = COMMAND.split(" ") + [message.encode("utf-8")]

    for x in range(5):
        out, err, code = run(command)
        if code == 0:
            return
        time.sleep(5)

    print "5 attempts to post a message to the chat room failed."


def main(feed_url):
    """Loads news from the specified feed, picks the latest one that wasn't
    posted to the jabber conference, and posts it."""
    history = read_history()

    for url, text in fetch_news(feed_url):
        if url not in history:
            history.append(url)
            send_news(url, text)
            write_history(history)
            break


if __name__ == "__main__":
    feed_url = "http://feeds.newsru.com/com/txt/news/big"
    if len(sys.argv) > 1:
        feed_url = sys.argv[1]
    main(feed_url)
