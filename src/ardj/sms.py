# encoding=utf-8

import logging
import urllib

import ardj.settings
import ardj.util

USAGE = """Usage: ardj sms number|all message...

When "all" is passed as the first argument, numbers are read from the file
specified in sms/subscribers (one number per line, sort of like CSV)."""


def send(number, message):
    if number == 'all':
        numbers = list(set([n.strip() for n in open(ardj.settings.getpath('sms/subscribers', fail=True), 'rb').read().split('\n') if n.strip()]))
        for number in numbers:
            send(number, message)
        return True

    if type(message) == unicode:
        message = message.encode('utf-8')

    api_key = ardj.settings.get('sms/api_key', fail=True)
    ardj.util.fetch('http://sms.ru/sms/send', args={
        'api_id': api_key,
        'to': number,
        'text': message,
    })
    logging.info('SMS sent to %s: %s' % (number, message))


def run_cli(args):
    if len(args) == 2:
        return send(args[0], args[1])
    print USAGE
