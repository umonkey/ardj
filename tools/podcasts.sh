#!/bin/sh
WORKDIR="."
SSH_REMOTE=radio@stream.tmradio.net
SSH_ARGS="-i $HOME/.config/tmradio/podcasts.pvt"
ROBOTS_DIR="/usr/lib/ardj/robots"

cd $(dirname $0)

# Download new episodes.
## nice -n 20 podget -d "$WORKDIR" -c podcasts.conf

# Transcode unsupported formats.
find podcasts -iregex '.*\.\(m4a\|m5a\)$' -exec sh podcasts.transcode {} \;

# Calculate replay gain.
find . -name '*.mp3' -exec nice -n 20 "$ROBOTS_DIR/normalizer" \{\} \; >/dev/null
find . -name '*.ogg' -exec nice -n 20 vorbisgain -f -q \{\} \;

# Upload.
find podcasts -type f -iregex '.*\.\(mp3\|ogg\)$' | while :; do
	read filepath || break
	filename=$(basename "$filepath")
	tags=$(basename $(dirname "$filepath"))
	echo "Uploading \"$filepath\"."
	scp -q -l 256 $SSH_ARGS "$filepath" $SSH_REMOTE:/tmp/ && \
	ssh $SSH_ARGS $SSH_REMOTE "ardj --tags=$tags --delete --add '/tmp/$filename'" && \
	rm "$filepath"
done
