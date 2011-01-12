#!/bin/sh
INCOMING_DIR=/home/$PAM_USER/incoming
IMPORT_SCRIPT_NAME=/usr/share/ardj/import-music-dir
RADIO_USER=radio

test -f /etc/ardj && . /etc/ardj

if [ -d "$INCOMING_DIR" -a "$PAM_TYPE" = "close_session" ]; then
	chmod -R g+w $INCOMING_DIR
	test -x $IMPORT_SCRIPT_NAME && su -c "$IMPORT_SCRIPT_NAME $INCOMING_DIR" $RADIO_USER
fi
