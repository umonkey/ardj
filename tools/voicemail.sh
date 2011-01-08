#!/bin/sh
#
# Voice mail processor for tmradio.net
#
# To process AMR files on Ubuntu you will need the libavcodec-extra-52 package
# from the Multiverse repository.
#
# @license Public Domain
# @author hex@umonkey.net (Justin Forest)
# @url http://tmradio.net/

REMOTE=radio@stream.tmradio.net

# Используем специальный публичный ключ, если есть.
SSH_ARGS=""
if [ -f "$HOME/.config/tmradio/voicemail.pvt" ]; then
	SSH_ARGS="-i $HOME/.config/tmradio/voicemail.pvt"
fi

FFMPEG=$(which ffmpeg)
if [ -z "$FFMPEG" ]; then
	echo "ERROR: please install ffmpeg." >&2
	exit 1
fi

test -n "$2" && SENDER="$2" || SENDER="Неизвестный слушатель"
test -n "$3" && SUBJECT="$3" || SUBJECT="Голосовая почта"

ffmpeg -y -i "$1" -ar 44100 -acodec vorbis -aq 90 -ab 256k -ac 2 "$1.ogg" >/dev/null
vorbiscomment -a "$1.ogg" -t "ARTIST=${SENDER}" -t "TITLE=${SUBJECT}"
vorbisgain -q "$1.ogg"

scp $SSH_ARGS "$1.ogg" $REMOTE:/tmp/voicemail.ogg
ssh $SSH_ARGS $REMOTE "ardj --tags=voicemail --delete --queue --add /tmp/voicemail.ogg"
rm "$1.ogg"
