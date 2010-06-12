deb:
	rm -rf debian/usr
	mkdir -p debian/usr/lib/python2.6
	cp -R src/ardj debian/usr/lib/python2.6/ardj
	cp -R bin debian/usr/bin
	cp -R share debian/usr/share
	find debian -name '*.pyc' -delete
	dpkg -b debian ardj.deb

install: deb
	sudo dpkg -i ardj.deb

back:
	scp tmradio.local:/usr/lib/python2.6/ardj/*.py src/ardj/

copy: deb
	scp ardj.deb tmradio.local:
	ssh -t tmradio.local 'sudo dpkg -i ardj.deb'
