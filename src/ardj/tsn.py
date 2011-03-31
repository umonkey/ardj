# vim: fileencoding=utf-8:

import glob
import os
import re
import sys
import time

import ardj.settings
import ardj.website

u"""Подготовка выпуска «Так себе новостей».

Скрипт должен:

- При запуске с параметром "prepare" создавать новую страницу для выпуска, с
  меткой "draft" (чтобы не уходило в RSS), куда можно будет добавить шоуноты.
  Запускается по крону, в начале эфира.
- При запуске с параметром "process" обрабатывать запись эфира, загружать её на
  веб-сервер, обновлять размер файла в описании выпуска.  Запускается по крону,
  примерно в полночь (когда уже точно эфир закончен).
- При запуске с параметром "email" отправлять сообщение в почтовую рассылку,
  вытаскивая ссылки из описания выпуска.  Запускается по крону, ночью.
"""

USAGE = u"""Usage: ardj tsn command

Commands:
  prepare   add a draft page to the web site
  process   clean up and transcode the live dump
  email     send last episode description to the mailing list
"""


PAGE_TEMPLATE = u"""title: Эфир ТСН от %(dd)s.%(mm)s.%(yyyy)s
date: %(yyyy)s-%(mm)s-%(dd)s 21:00
file: http://files.tmradio.net/audio/sosonews/sosonews-%(episode)02u.mp3
filesize: 100000000
labels: draft, umonkey, dugwin, tsn, новости, podcast
---
Основные новости:

- Ссылки пока отсутствуют...

![статистика](http://files.tmradio.net/audio/sosonews/sosonews-%(episode)02u.png)
"""


EMAIL_SUBJECT = u"Выпуск №%(episode)02u от %(dd)s.%(mm)s.%(yyyy)s"
EMAIL_TEMPLATE = u"""Скачать выпуск:
http://files.tmradio.net/audio/sosonews/sosonews-%(episode)02u.mp3

Обсуждение:
http://www.tmradio.net/programs/tsn/%(episode)02u/

Основные темы:

%(links)s
"""

def find_last_episode():
    web_dir = ardj.settings.getpath('website/root_dir', fail=True)
    return max(glob.glob(os.path.join(web_dir, 'input/programs/tsn/*/index.md')))

def run_prepare():
    filename = find_last_episode()
    page = ardj.website.load_page(filename)

    labels = [l.strip() for l in page['labels'].split(',')]
    if 'draft' in labels:
        print >>sys.stderr, 'ERROR: last page has the "draft" label.'
        return 1

    parts = filename.split(os.path.sep)
    next_id = parts[-2] = str(int(parts[-2]) + 1)
    filename = os.path.sep.join(parts)

    text = PAGE_TEMPLATE % {
        'dd': time.strftime('%d'),
        'mm': time.strftime('%m'),
        'yyyy': time.strftime('%Y'),
        'episode': int(next_id),
    }

    os.mkdir(os.path.dirname(filename))
    open(filename, 'wb').write(text.encode('utf-8'))
    
    print 'Wrote %s' % filename
    ardj.website.update()

def run_email():
    filename = find_last_episode()
    page = ardj.website.load_page(filename)
    page_id = int(filename.split(os.path.sep)[-2])

    links = u''.join([u'- %s\n  %s\n' % (l[1], l[0]) for l in re.findall('<a href="([^"]+)">([^<]+)</a>', page['text'])])

    args = {
        'dd': time.strftime('%d'),
        'mm': time.strftime('%m'),
        'yyyy': time.strftime('%Y'),
        'episode': int(page_id),
        'links': links.strip(),
    }

    text = EMAIL_TEMPLATE % args
    subject = EMAIL_SUBJECT % args

    print text

def run(args):
    args = args or ['default']

    if args[0] == 'prepare':
        return run_prepare()
    if args[0] == 'email':
        return run_email()

    print USAGE
    return 1
