import os
import subprocess
import sys
import tempfile

# email sending
import smtplib
from email import encoders
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase

import ardj.log
import ardj.settings

def run(command):
    command = [str(x) for x in command]
    ardj.log.debug('> ' + ' '.join(command))
    subprocess.Popen(command).wait()
    return True

class mktemp:
    def __init__(self, suffix=''):
        self.filename = tempfile.mkstemp(prefix='ardj_', suffix=suffix)[1]
        os.chmod(self.filename, 0664)

    def __del__(self):
        if os.path.exists(self.filename):
            ardj.log.debug('Deleting temporary file %s' % self.filename)
            os.unlink(self.filename)

    def __str__(self):
        return self.filename

    def __unicode__(self):
        return unicode(self.filename)

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

def send_mail_cli(args):
    if not args:
        print 'Usage: ardj mail to [subject]'
        return 1
    if len(args) < 2:
        args.append('no subject')
    send_mail([args[0]], args[1], sys.stdin.read())
