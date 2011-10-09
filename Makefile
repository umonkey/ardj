VERSION=1.0.1
ARCH=`uname -m`
DEB=ardj_${VERSION}-$(ARCH).deb
ZIP=ardj_${VERSION}.zip
TAR=ardj_${VERSION}.tar.gz

all:

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
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml python unittests/all.py
	rm -f unittests/data/*.*

console:
	PYTHONPATH=src ./bin/ardj console $(MAIL)

install:
	sudo VERSION=$(VERSION) python setup.py install --record install.log

uninstall:
	cat install.log | xargs sudo rm -f

purge:
	sudo rm -rf /var/lib/ardj /var/log/ardj

release: clean bdist deb
	hg archive -t zip ardj-${VERSION}.zip
	googlecode_upload.py -s "ardj v${VERSION} (Debian)" -p ardj -l Featured,Type-Package,OpSys-Linux ardj-${VERSION}.deb
	googlecode_upload.py -s "ardj v${VERSION} (Source)" -p ardj -l Featured,Type-Source,OpSys-All ardj-${VERSION}.zip
	googlecode_upload.py -s "ardj v${VERSION} (Other)" -p ardj -l Featured,Type-Source,OpSys-All ardj-${VERSION}.tar.gz

clean:
	find -regex '.*\.\(pyc\|rej\|orig\|deb\|zip\|tar\.gz\)$$' -delete

bdist: test clean
	VERSION=$(VERSION) python setup.py bdist
	mv dist/*.tar.gz $(TAR)
	rm -rf build dist

deb: bdist
	rm -rf packages/debian/usr
	tar xfz $(TAR) -C packages/debian
	mv packages/debian/usr/local/* packages/debian/usr/
	rm -rf packages/debian/usr/local
	fakeroot dpkg -b packages/debian $(DEB)
	rm -rf packages/debian/usr packages/debian/etc

serve:
	PYTHONPATH=$(pwd)/src ./bin/ardj serve

docs:
	mkdir -p share/doc/ardj/pydoc
	rm -f share/doc/ardj/pydoc/*.html
	ls -1 src/ardj/*.py | grep -v __init__ | cut -d/ -f3 | cut -d. -f1 | sed -re 's/(.*)/ardj.\1/g' | xargs pydoc -w ardj
	mv *.html share/doc/ardj/pydoc/
