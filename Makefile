VERSION=1.0-$(shell date +'%Y.%m.%d.%H%M')
DEB=ardj-${VERSION}.deb
ZIP=ardj-${VERSION}.zip
TAR=ardj-${VERSION}.tar.gz

help:
	@echo "bdist      -- prepares a tar.gz"
	@echo "clean      -- removes temporary files"
	@echo "deb        -- prepare a Debian package"
	@echo "install    -- install using setup.py"
	@echo "release    -- upload a new version to Google Code"
	@echo "test       -- runs unit tests"
	@echo "uninstall  -- uninstall (installs first to find installed files)"

test:
	cp -f unittests/data/src/* unittests/data/
	rm -f tests.log tests-ardj.log
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml python unittests/all.py || cat tests.log
	rm -f unittests/data/*.*

testv: test
	less -S tests-ardj.log

install:
	sudo python setup.py install --record install.log

uninstall:
	cat install.log | xargs sudo rm -f

release: clean deb
	hg archive -t zip ardj-${VERSION}.zip
	googlecode_upload.py -s "ardj v${VERSION}" -p ardj -l Featured,Type-Package,OpSys-Linux ardj-${VERSION}.deb
	googlecode_upload.py -s "ardj v${VERSION}" -p ardj -l Featured,Type-Source,OpSys-All ardj-${VERSION}.zip

clean:
	find -regex '.*\.\(pyc\|rej\|orig\|deb\|zip\|tar\.gz\)$$' -delete

bdist: clean ices/ices.ardj
	python setup.py bdist
	mv dist/*.tar.gz ${TAR}
	rm -rf build dist

deb: bdist
	rm -rf *.deb debian/usr
	cat debian/DEBIAN/control.in | sed -e "s/VERSION/${VERSION}/g" > debian/DEBIAN/control
	tar xfz ${TAR} -C debian
	mv debian/usr/local/* debian/usr/
	rm -rf debian/usr/local
	fakeroot dpkg -b debian ${DEB}
	rm -rf debian/usr debian/DEBIAN/control

ices/ices.ardj:
	make -C ices
