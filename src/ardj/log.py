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
import traceback

import ardj.settings


def get_level():
    """Returns the configured logging level."""
    level = ardj.settings.get("log_level", "info").lower()

    if level == "debug":
        return logging.DEBUG
    if level == "info":
        return logging.INFO
    if level == "warning":
        return logging.WARNING
    if level == "error":
        return logging.ERROR

    return logging.CRITICAL


def install_syslog(name):
    """Makes use of the syslog."""
    logger = logging.getLogger()
    logger.setLevel(get_level())

    device = ardj.settings.getpath("log_device", "/dev/log")
    syslog = logging.handlers.SysLogHandler(address=device)

    format_string = ardj.settings.get(
        "log_format_string",
        name + "[%(process)d]: %(levelname)s %(message)s")
    formatter = logging.Formatter(format_string)
    syslog.setFormatter(formatter)

    logger.addHandler(syslog)


def install_file(filename, name):
    """Adds a custom formatter and a rotating file handler to the default
    logger."""
    folder = os.path.dirname(filename) or "."
    if not os.path.exists(folder) or not os.access(folder, os.W_OK):
        raise Exception("Can't log to %s: no write permissions." % filename)

    max_size = ardj.settings.get("log_max_size", 1000000)
    max_count = ardj.settings.get("log_max_files", 5)

    logger = logging.getLogger()
    logger.setLevel(get_level())

    handler = logging.handlers.RotatingFileHandler(
        filename, maxBytes=max_size, backupCount=max_count)

    handler.setFormatter(
        logging.Formatter(
            '%%(asctime)s - %s[%%(process)6d] - %%(levelname)s - %%(message)s' %
            name))
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)


def install(name=None):
    """Configures logging according to the log setting."""
    target = ardj.settings.getpath("log", "syslog")

    if name is None:
        name = "ardj"

    if target == "syslog":
        return install_syslog(name)
    return install_file(target, name)


def log_error(msg):
    """Logs an error message line by line (syslog friendly)."""
    msg = msg.strip() + "\n" + traceback.format_exc()
    for line in msg.strip().split("\n"):
        logging.error(line)


def log_info(msg, *args, **kwargs):
    """Log a string with the info level."""
    try:
        msg = msg.format(*args, **kwargs)
    except UnicodeEncodeError:
        msg = str(msg).format(*args, **kwargs)

    if isinstance(msg, str):
        msg = msg.encode("utf-8")

    logging.info(msg)


__all__ = ["install", "log_error"]
