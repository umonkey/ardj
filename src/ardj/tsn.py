# vim: fileencoding=utf-8:

import feedparser
import glob
import logging
import os
import re
import sys
import time

import ardj.mail
import ardj.settings
import ardj.util
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


PAGE_TEMPLATE = u"""title: ТСН №%(episode)02u от %(dd)s.%(mm)s.%(yyyy)s
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
http://tsn.tmradio.net/%(episode)02u

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
        logging.error('Last page has the "draft" label.')
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
    
    logging.info('Wrote %s' % filename)
    ardj.website.update()

def find_tsn_url():
    news_feed = ardj.settings.get('tsn/live_feed')
    if not news_feed:
        logging.debug('tsn/live_feed not set.')
        return None

    filename = find_last_episode()
    page = ardj.website.load_page(filename)
    page_date = page['date'].split(' ')[0].replace('-', '')

    feed = feedparser.parse(news_feed)
    for entry in feed['entries']:
        for enc in entry['enclosures']:
            efn = enc['href'].split('/')[-1]
            if efn.startswith('live-') and efn.endswith('.mp3'):
                parts = efn.split('.')[0].split('-')
                efn_time = int(parts[2])
                if page_date == parts[1]:
                    if efn_time >= 2030 and efn_time < 2200:
                        return enc['href']

    print "The feed doesn't have anything interesting."

def run_process():
    tsn_url = find_tsn_url()
    if not tsn_url:
        return 0

    filename = ardj.util.fetch(tsn_url)
    if filename is None:
        logging.error('Could not fetch %s' % tsn_url)
        return 1

    output_wav = ardj.util.mktemp(suffix='.wav')
    command = [ 'sox', filename, output_wav ]

    if ardj.settings.get('tsn/noise/profile'):
        command.append('noisered')
        command.append(ardj.settings.getpath('tsn/noise/profile'))
        command.append(ardj.settings.get('tsn/noise/level', '0.3'))

        if ardj.settings.get('tsn/silence'):
            strength = ardj.settings.get('tsn/silence/strength', '0.2')
            level = ardj.settings.get('tsn/silence/level', '-50d')
            command.append('silence')
            command.append('-l')
            command.append('1')
            command.append(strength)
            command.append(level)
            command.append('-1')
            command.append(strength)
            command.append(level)

    command.append('norm')
    ardj.util.run(command)

    output_mp3 = ardj.util.mktemp(suffix='.mp3')
    mp3_bitrate = ardj.settings.get('tsn/mp3_bitrate', '96')
    ardj.util.run([ 'lame', '-m', 'm', '-b', mp3_bitrate, '-B', mp3_bitrate, '--resample', '44100', output_wav, output_mp3 ])

    ardj.util.run([ 'mp3gain', output_mp3 ])

    tags = ardj.tags.get(output_mp3)
    tags['artist'] = u'Тоже мне радио'
    tags['album'] = u'Так себе новости'
    tags['title'] = u'Выпуск ТСН от %s' % time.strftime('%d.%m.%Y') # FIXME: брать из заголовка страницы
    ardj.tags.set(output_mp3, tags)

def run_email():
    to = ardj.settings.get('tsn/mail_to', None)
    if not to:
        logging.debug('tsn/mail_to not set, not sending email.')
        return 0

    filename = find_last_episode()
    page = ardj.website.load_page(filename)
    page_id = int(filename.split(os.path.sep)[-2])

    links = u''.join([u'- %s\n  %s\n' % (l[1], l[0]) for l in re.findall('<a href="([^"]+)">([^<]+)</a>', page['text'])])
    page_date = time.strptime(page['date'][:10], '%Y-%m-%d')

    args = {
        'dd': time.strftime('%d', page_date),
        'mm': time.strftime('%m', page_date),
        'yyyy': time.strftime('%Y', page_date),
        'episode': int(page_id),
        'links': links.strip(),
    }

    text = EMAIL_TEMPLATE % args
    subject = EMAIL_SUBJECT % args

    ardj.mail.send_mail(to, subject, text)

def run(args):
    args = args or ['default']

    if args[0] == 'prepare':
        return run_prepare()
    if args[0] == 'process':
        return run_process()
    if args[0] == 'email':
        return run_email()

    print USAGE
    return 1
