"""
The main command line entry module.
"""

import sys
import ardj.server
import ardj.scrobbler
import ardj.tracks

def main(prog, command=None, *argv):
    if command == "jabber":
        ardj.jabber.cmd_run_bot()
    elif command == "next-track":
        ardj.tracks.cmd_next()
    elif command == "scrobbler":
        ardj.scrobbler.cmd_start()
    elif command == "serve":
        ardj.server.cmd_serve()
    elif command == "scan":
        ardj.tracks.cmd_scan()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        exit(1)

if __name__ == "__main__":
    main(*sys.argv)
