# vim: set fileencoding=utf-8:

"""Interface to the mailbox."""

import sys

# email sending
import smtplib
from email import encoders
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase

# local modules
import ardj.util


USAGE = """Usage: ardj mail [command]

Commands:
  send addr [subject]   -- send message from stdin to addr
"""

def send_mail(to, subject, message, files=None):
    if files and type(files) != list:
        files = [files]
    if type(to) != list:
        to = [to]

    if type(message) == unicode:
        message = message.encode('utf-8')

    msg = MIMEMultipart()
    msg.attach(MIMEText(message, _charset='utf-8'))

    if files:
        for filename in files:
            att = MIMEBase('application', 'octet-stream')
            attname = os.path.basename(filename)
            data = file(filename, 'rb').read()

            att.set_payload(data)
            encoders.encode_base64(att)
            att.add_header('content-disposition', 'attachment', filename=attname)
            msg.attach(att)

    login = ardj.settings.get('mail/smtp/login', fail=True)
    password = ardj.settings.get('mail/smtp/password', fail=True)

    msg['Subject'] = subject
    msg['From'] = ardj.settings.get('mail/from', login)

    msg['To'] = to[0]
    if len(to) > 1:
        msg['Cc'] = ', '.join(to[1:])

    s = smtplib.SMTP(ardj.settings.get('mail/smtp/server', 'smtp.gmail.com'), int(ardj.settings.get('mail/smtp/port', '25')))
    s.ehlo()
    if ardj.settings.get('mail/smtp/tls') == True:
        s.starttls()
    s.ehlo()
    s.login(login, password)
    s.sendmail(login, to, msg.as_string())
    s.quit()

    ardj.log.info('Sent mail to %s' % to[0])

def run_cli(args):
    if len(args) >= 2 and args[0] == 'send':
        args.append('no subject')
        return send_mail([args[1]], args[2], sys.stdin.read())
    print USAGE
