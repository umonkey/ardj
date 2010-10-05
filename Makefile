VERSION=1.0-$(shell date +'%Y.%m.%d.%H%M')

help:
	@echo "Targets: deb install release back copy clean."

deb: ices/ices
	rm -rf *deb *zip
	cat debian/DEBIAN/control.in | sed -e "s/VERSION/${VERSION}/g" > debian/DEBIAN/control
	mkdir -p debian/usr/lib/python2.6
	cp -R src/ardj debian/usr/lib/python2.6/ardj
	cp -R bin debian/usr/bin
	cp -R share debian/usr/share
	cp ices/ices debian/usr/bin/ices.ardj
	strip debian/usr/bin/ices.ardj
	find debian -name '*.pyc' -delete
	sudo chown -R root:root debian/usr
	dpkg -b debian ardj-${VERSION}.deb
	sudo rm -rf debian/usr

ices/ices:
	make -C ices

install: deb
	sudo dpkg -i ardj-${VERSION}.deb

release: clean deb
	hg archive -t zip ardj-${VERSION}.zip
	googlecode_upload.py -s "ardj v${VERSION}" -p ardj -l Featured,Type-Package,OpSys-Linux ardj-${VERSION}.deb
	googlecode_upload.py -s "ardj v${VERSION}" -p ardj -l Featured,Type-Source,OpSys-All ardj-${VERSION}.zip

back:
	scp -Bq tmradio.local:/usr/lib/python2.6/ardj/*.py src/ardj/

copy: deb
	scp -Bq ardj-${VERSION}.deb tmradio.local:
	ssh -t tmradio.local 'sudo dpkg -i ardj-${VERSION}.deb; rm -f ardj-*.deb'

clean:
	rm -rf *deb *zip
