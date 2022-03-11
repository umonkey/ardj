#!/bin/sh
set -e

if [ -n "$UID" -a -n "$GID" ]; then
    addgroup --gid "$GID" radio
    adduser --home /app --disabled-password -H -g "" -u "$UID" -G radio radio
else
    addgroup --gid "1000" radio
    adduser --home /app --disabled-password -H -g "" -u "1000" -G radio radio
fi

if [ ! -f /app/data/ardj.yaml ]; then
    echo "Populating /app/data with pre-defined files."
    mkdir -p /app/data
    cp -Rnv /app/data.dist/* /app/data/
fi

chmod 640 /app/data/ezstream.xml
chown radio:radio /app/data/*.*

echo "Initializing the database..."
python3 -m ardj db-init

echo "Scanning the music folder..."
python3 -m ardj scan

echo "Starting the components..."
exec /usr/bin/supervisord -nc /etc/supervisord.conf
