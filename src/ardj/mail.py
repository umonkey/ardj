# encoding=utf-8

import logging
import subprocess

from smtplib import SMTP
from email.encoders import encode_base64
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText

from ardj import settings


def utf8(s):
    if isinstance(s, unicode):
        s = s.encode("utf-8")
    else:
        s = str(s)
    return s


class Mailer(object):
    def deliver(self):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = self.get_subject()
        msg["From"] = self.get_sender()
        msg["To"] = self.get_recipient()
        msg["X-Mailer"] = "ardj/%s" % self.__class__.__name__

        text = self.get_html_body()
        if text is not None:
            part = MIMEText(utf8(text), _subtype="html", _charset="utf-8")
            msg.attach(part)

        text = self.get_plain_body()
        if text is not None:
            part = MIMEText(utf8(text), _subtype="plain", _charset="utf-8")
            msg.attach(part)

        raw_msg = msg.as_string()
        logging.debug(raw_msg)

        p = subprocess.Popen(["sendmail", self.get_recipient()],
            stdin=subprocess.PIPE)
        p.communicate(raw_msg)

    def get_subject(self):
        return "No subject"

    def get_sender(self):
        return "ardj@umonkey.net"

    def get_recipient(self):
        raise RuntimeError("Please override get_recipient.")

    def get_html_body(self):
        return None

    def get_plain_body(self):
        return None

    def get_template_data(self, suffix, default, vars=None):
        name = "%s_%s" % (self.__class__.__name__, suffix)

        template = settings.get(name, default)
        if template is None:
            return None

        if isinstance(vars, dict):
            template = template.format(**vars)

        return template


class TokenMailer(Mailer):
    subject_template = u"Your token is ready"

    plain_template = u"Please open this link to validate your token:\n\n{link}"

    def __init__(self, recipient, token):
        self.recipient = recipient
        self.token = token

    def get_recipient(self):
        return self.recipient

    def get_subject(self):
        return self.get_template_data("subject",
            self.subject_template)

    def get_plain_body(self):
        return self.get_template_data("plain",
            self.plain_template,
            self.get_body_vars())

    def get_html_body(self):
        return self.get_template_data("html",
            None,
            self.get_body_vars())

    def get_body_vars(self):
        base_url = settings.get("web_api_root", "http://localhost:8080").rstrip("/")
        link = "%s/auth?token=%s" % (base_url, self.token)

        return {
            "token": self.token,
            "link": link,
        }
