# encoding=utf-8

"""ARDJ, an artificial DJ.

This module installs a custom logger that writes messages to a text file.

To use the module, call the install() method before logging anything.  This is
done automatically when you use the CLI interface, so you only need to use this
module explicitly if you're importing parts of ardj into your existing code.
"""

import logging
import logging.handlers
import os

import ardj.settings


def install():
    """Adds a custom formatter and a rotating file handler to the default
    logger."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    h = logging.handlers.RotatingFileHandler(ardj.settings.getpath('log', '/tmp/ardj.log'), maxBytes=1000000, backupCount=5)
    h.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    h.setLevel(logging.DEBUG)
    logger.addHandler(h)
