#!/bin/sh
ICES=../ices

if [ -n "$1" -a -x "$1" ]; then
	ICES="$1"
fi

make -C samples

echo "Testing $ICES"
if [ ! -x "$ICES" ]; then
	echo "$ICES is not there."
	exit 1
fi

echo $ICES -C $(pwd)/ -c ices.conf
$ICES -C $(pwd)/ -c ices.conf -v
