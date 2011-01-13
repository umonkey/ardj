#!/bin/sh
SSH_REMOTE="radio@stream.tmradio.net"
SSH_ARGS="-i $HOME/.config/tmradio/fetch-news.pvt"
FORMAT=ogg

PROBLEMS=$HOME/.cache/fetch-news-failed

cd $(dirname $0)

# fetch the new one
echo "Fetching news."
http_proxy= mplayer -ao pcm:file=news.wav http://broadcast.echo.msk.ru:9000/content/current.mp3 >/dev/null 2>&1
if [ -f news.wav ]; then
	FILESIZE=$(stat -c'%s' news.wav)
	if [ $FILESIZE -ge 100000000 ]; then
		echo "Too many news (broken?), ignoring." >&2
		ls -ldh news.wav
		exit 1
	fi

	ARTIST="Echo of Moscow"
	TITLE="News from $(date +'%d.%m.%Y %H:%M')"

	if [ $FORMAT = "ogg" ]; then
		FILENAME=news.ogg
		echo "Transcoding to OGG/Vorbis."
		oggenc -Q -a "$ARTIST" -t "$TITLE" -o $FILENAME news.wav && rm -f news.wav
		echo "Calculating ReplayGain."
		vorbisgain -q $FILENAME
	elif [ $FORMAT = "mp3" ]; then
		FILENAME=news.mp3
		echo "Transcoding to MP3."
		lame --ta "$ARTIST" --tt "$TITLE" news.wav $FILENAME
		rm -f news.wav
		echo "Calculating ReplayGain."
		mp3gain $FILENAME
	fi
	echo "Uploading to $SSH_REMOTE"
	scp -l 128 -q $SSH_ARGS $FILENAME $SSH_REMOTE:
	echo "Adding to the database."
	ssh $SSH_ARGS $SSH_REMOTE "ardj --sql \"UPDATE tracks SET weight = 0 WHERE artist = 'Echo of Moscow'\"; ardj --tags=news --delete --queue --add \"${FILENAME}\""
	echo "Cleaning up."
	rm -rf $FILENAME

	if [ -f "$PROBLEMS" ]; then
		rm -f "$PROBLEMS"
		echo "Новости Эха Москвы снова в эфире." | bti-tmradio
	fi
else
	echo "Could not fetch news."

	if [ ! -f "$PROBLEMS" ]; then
		touch "$PROBLEMS"
		echo "Наблюдаются проблемы с новостями Эха Москвы." | bti-tmradio
	fi
fi
