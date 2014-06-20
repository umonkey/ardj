# encoding=utf-8

"""
Command line interface library for ardj

Implements CLI argument parsing, subcommand handling, formats USAGE messages.
Typically you define functions named cmd_xyz, docstring them, then call the
CLI like this:

>>> import sys
>>> from ardj.cli import cli_main
>>> cli_main(globals(), *sys.argv)

The rest is done automatically.
"""

__author__ = "Justin Forest <hex@umonkey.net>"


import os
import sys


class UsageError(RuntimeError):
    pass


def fail(msg):
    print >> sys.stderr, msg
    sys.exit(1)


def match_command(command, gl):
    prefix = "cmd_" + command.replace("-", "_")

    options = []
    for k, v in gl.items():
        if k == command:
            return v
        elif k.startswith(prefix):
            options.append((k.replace("_", "-"), v))

    if len(options) == 1:
        return options[0][1]

    elif not options:
        return None

    names = [k for k, v in options]
    fail("Ambiguous command, please narrow your choice: %s." % ", ".join(names))


def strip_cmd(name):
    return name[4:].replace("_", "-")


def format_doc(doc):
    lines = doc.strip().split("\n")
    return lines[0].strip().rstrip(".")


def format_usage(program, gl):
    """Returns the formatted USAGE message for the specified context."""
    prefix = "Usage:"

    if os.path.exists(program):
        program = os.path.basename(program)

    funcs = [(strip_cmd(k), v)
        for k, v in gl.items()
        if k.startswith("cmd_")]
    if not funcs:
        fail("This module provides no CLI commands.")

    maxlen = max([len(k) for k, v in funcs])

    msg = []
    for k, v in sorted(funcs):
        if not v.__doc__:
            continue
        msg.append("%s %s %s  -- %s" % (prefix, program,
            k.ljust(maxlen), format_doc(v.__doc__)))
        prefix = " " * len(prefix)

    if not msg:
        fail("This module provides no public commands.")

    return "\n".join(msg)


def convert_gl(gl):
    if isinstance(gl, dict):
        return gl

    return {k: getattr(gl, k)
        for k in dir(gl)}


def parse_args(argv):
    args = []
    kwargs = {}

    for arg in argv:
        if arg.startswith("--") and "=" in arg:
            k, v = arg[2:].split("=", 1)
            kwargs[k] = v

        elif arg.startswith("--"):
            kwargs[arg[2:]] = True

        else:
            args.append(arg)

    return args, kwargs


def cli_main(gl, program, command=None, *argv):
    """Main CLI entry point."""
    gl = convert_gl(gl)

    if command is None:
        fail(format_usage(program, gl))

    func = match_command(command, gl)
    if func is None:
        fail("Unknown command: %s\n%s" % (command, format_usage(program, gl)))

    try:
        if func(*argv) is False:
            sys.exit(1)
        else:
            sys.exit(0)
    except UsageError, e:
        print >> sys.stderr, e
        sys.exit(1)


__all__ = ["cli_main"]
