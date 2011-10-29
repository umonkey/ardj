VERSION=1.0.4
TAR=ardj-${VERSION}.tar.gz
DEB=ardj_${VERSION}-1_all.deb

build:
	@echo "This is a Python package, you don't need to build it.  Available commands:"
	@echo "make clean                     -- removes temporary files"
	@echo "make doc                       -- build the docbook"
	@echo "make install                   -- install using setup.py"
	@echo "make install [DESTDIR=./tmp]   -- install ardj"
	@echo "make package-ubuntu            -- create source and binary packages"
	@echo "make test                      -- runs unit tests"
	@echo "make test-syntax               -- runs PEP8 check"

test: test-syntax clean
	cp -f unittests/data/src/* unittests/data/
	rm -f tests.log tests-ardj.log
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml python unittests/all.py
	rm -f unittests/data/*.*

test-syntax:
	pep8 -r --ignore=E501 --exclude=twitter.py,socks.py,jabberbot.py src/ardj/*.py unittests/*.py

console:
	PYTHONPATH=src ./bin/ardj console $(MAIL)

install: share/doc/man/ardj.1.gz
	VERSION=$(VERSION) python setup.py install --root=$(DESTDIR)
	mkdir -p $(DESTDIR)/usr/bin
	mv $(DESTDIR)/usr/local/bin/ardj $(DESTDIR)/usr/bin/ardj
	rm -rf build

uninstall:
	cat install.log | xargs sudo rm -f

purge:
	sudo rm -rf /var/lib/ardj /var/log/ardj*

tar: doc man clean
	mkdir ardj-$(VERSION)
	cp -R bin doc share src unittests packages/debian Makefile README.md TODO setup.py ardj-$(VERSION)/
	tar cfz $(TAR) ardj-$(VERSION)
	rm -rf ardj-$(VERSION)

package-debian: tar
	mkdir -p tmp
	cp $(TAR) tmp/ardj-$(VERSION).tar.gz
	cp $(TAR) tmp/ardj_$(VERSION).orig.tar.gz
	tar xfz ardj-$(VERSION).tar.gz --directory tmp
	cd tmp/ardj-$(VERSION) && debuild -S
	mv tmp/ardj_$(VERSION)[_-]* ./
	rm -rf tmp

upload-ppa:
	dput ardj ardj_$(VERSION)-*.changes

release: package-debian
	googlecode_upload.py -s "ardj v${VERSION} (Source)" -p ardj -l Featured,Type-Source,OpSys-All ${TAR}
	googlecode_upload.py -s "ardj v${VERSION} (Debian)" -p ardj -l Featured,Type-Source,OpSys-Debian ${DEB}

clean:
	test -d .hg && hg clean || true
	rm -rf doc/book.xml share/doc/man/ardj.1.gz tests.log tmp
	find -regex '.*\.\(pyc\|rej\|orig\|zip\|tar\.gz\)$$' -delete

bdist: clean
	VERSION=$(VERSION) python setup.py bdist
	mv dist/*.tar.gz $(TAR)
	rm -rf build dist

zsh-completion: share/shell-extensions/zsh/_ardj

share/shell-extensions/zsh/_ardj: src/ardj/cli.py
	PYTHONPATH=src python bin/ardj --zsh > $@

serve:
	PYTHONPATH=$(pwd)/src ./bin/ardj serve

share/doc/man/ardj.1: src/docbook/man.xml
	docbook2x-man src/docbook/man.xml
	mkdir -p share/doc/man
	mv ardj.1 share/doc/man/ardj.1

share/doc/man/ardj.1.gz: share/doc/man/ardj.1
	gzip -f9 < share/doc/man/ardj.1 > share/doc/man/ardj.1.gz

man: share/doc/man/ardj.1

doc:
	make -C doc VERSION=$(VERSION)

.PHONY: doc clean tar
