VERSION=1.0-$(shell date +'%Y.%m.%d.%H%M')

deb:
	rm -rf debian/usr
	cat debian/DEBIAN/control.in | sed -e "s/VERSION/${VERSION}/g" > debian/DEBIAN/control
	mkdir -p debian/usr/lib/python2.6
	cp -R src/ardj debian/usr/lib/python2.6/ardj
	cp -R bin debian/usr/bin
	cp -R share debian/usr/share
	find debian -name '*.pyc' -delete
	dpkg -b debian ardj-${VERSION}.deb

install: deb
	sudo dpkg -i ardj-${VERSION}.deb

back:
	scp tmradio.local:/usr/lib/python2.6/ardj/*.py src/ardj/

copy: deb
	scp ardj-${VERSION}.deb tmradio.local:
	ssh -t tmradio.local 'sudo dpkg -i ardj-${VERSION}.deb'
