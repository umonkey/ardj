#!/usr/bin/env python

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
import subprocess
import sys
import urllib

import feedparser


HISTFILE = "~/.newswire"
HISTSIZE = 100
COMMAND = "ardj xmpp-send"


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
        return urllib.urlopen("http://clck.ru/--?url=" + url).read()
    except:
        return url


def send_news(url, text):
    """Sends the news to the chat room."""
    message = u"%s: %s" % (text, short_url(url))
    command = COMMAND.split(" ") + [message.encode("utf-8")]
    subprocess.Popen(command).wait()


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
