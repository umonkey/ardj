deb:
	rm -rf debian/usr
	mkdir -p debian/usr/lib/python2.6
	cp -R src debian/usr/lib/python2.6/ardj
	cp -R bin debian/usr/bin
	cp -R share debian/usr/share
	dpkg -b debian ardj.deb

install: deb
	sudo dpkg -i ardj.deb
