# encoding=utf-8

"""The new CLI wrapper for ardj."""


import sys


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

    names = [k for k, v in options]
    fail("Ambiguous command, please narrow your choice: %s." % ", ".join(names))


def strip_cmd(name):
    return name[4:].replace("_", "-")


def format_usage(program, gl):
    """Returns the formatted USAGE message for the specified context."""
    prefix = "Usage:"

    funcs = [(strip_cmd(k), v)
        for k, v in gl.items()
        if k.startswith("cmd_")]

    maxlen = max([len(k) for k, v in funcs])

    msg = []
    for k, v in funcs:
        msg.append("%s %s %s  -- %s" % (prefix, program,
            k.ljust(maxlen), "wtf"))

    return "\n".join(msg)


def cli_main(gl, program, command=None, *argv):
    """Main CLI entry point."""
    if command is None:
        fail(format_usage(program, gl))

    func = match_command(command, gl)
    if func(*argv) is False:
        sys.exit(1)
    else:
        sys.exit(0)


__all__ = ["cli_main"]
