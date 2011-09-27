# encoding=utf-8

"""Logging for ardj.

Installs a custom logger that writes messages to a text file.
"""

import logging
import logging.handlers
import os

import ardj.settings


def install():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    h = logging.handlers.RotatingFileHandler(ardj.settings.getpath('log', '~/ardj.log'), maxBytes=1000000, backupCount=5)
    h.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)
