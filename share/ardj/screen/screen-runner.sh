#!/bin/sh
#
# Screen script for ardj. To run from cron use this syntax:
#
#   @reboot /usr/share/ardj/screen/screen-runner.sh
#
# More info at:
# http://www.plouj.com/blog/2008/03/31/howto-run-rtorrent-from-cron-inside-screen/

DIR=$(dirname $0)
/usr/bin/screen -fa -d -m -S ardj -c ${DIR}/screenrc
