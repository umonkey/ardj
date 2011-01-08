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

for binary in ffmpeg oggenc sox vorbisgain; do
	if [ -z "$binary" ]; then
		echo "ERROR: please install ${binary}." >&2
		exit 1
	fi
done

if [ -z "$1" ]; then
	echo "Usage: $0 sound_file_name [sender_email [subject]]"
	exit 1
fi

test -n "$2" && SENDER="$2" || SENDER="Неизвестный слушатель"
test -n "$3" && SUBJECT="$3" || SUBJECT="Голосовая почта"

ffmpeg -y -i "$1" -ar 44100 -ac 1 "$1.wav" >/dev/null

PRE="$HOME/.config/tmradio/voicemail-pre.wav"
POST="$HOME/.config/tmradio/voicemail-post.wav"
if [ -f "$PRE" -a -f "$POST" ]; then
	sox --norm "$PRE" "$1.wav" "$POST" "$1.wav.wav"
	mv "$1.wav.wav" "$1.wav"
fi

oggenc -Q -q 9 -a "$SENDER" -t "$SUBJECT" "$1.wav"
vorbisgain -q "$1.ogg"

scp $SSH_ARGS "$1.ogg" $REMOTE:/tmp/voicemail.ogg
ssh $SSH_ARGS $REMOTE "ardj --tags=voicemail --delete --queue --add /tmp/voicemail.ogg"
rm "$1.ogg"
