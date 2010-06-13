#!/bin/sh

DIR=$(dirname $0)
/usr/bin/screen -fa -d -m -S ardj -c ${DIR}/screenrc
