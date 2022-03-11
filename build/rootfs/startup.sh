#!/bin/sh
set -e

if [ -n "$UID" -a -n "$GID" ]; then
    addgroup --gid "$GID" radio
    adduser --home /app --disabled-password -H -g "" -u "$UID" -G radio radio
else
    addgroup --gid "1000" radio
    adduser --home /app --disabled-password -H -g "" -u "1000" -G radio radio
fi

mkdir -p /app/data
test -f /app/data/ezstream.xml || cp /app/data.dist/ezstream.xml /app/data/
test -f /app/data/icecast2.xml || cp /app/data.dist/icecast2.xml /app/data/
test -f /app/data/playlist.yaml || cp /app/data.dist/playlist.yaml /app/data/
test -f /app/data/ardj.yaml || cp /app/data.dist/ardj.yaml /app/data/
test -d /app/data/music || cp -R /app/data.dist/music /app/data/

chmod 640 /app/data/ezstream.xml
chown radio:radio /app/data/*.*

python3 -m ardj scan
exec /usr/bin/supervisord -nc /etc/supervisord.conf
