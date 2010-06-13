# This script keeps ices running.  Useful to prevent unplanned
# station outage.

if [ ! -x /usr/bin/ices ]; then
	echo "Please install ices first." >&2
	exit 1
fi

while :; do
	/usr/bin/ices
	sleep 5
done
