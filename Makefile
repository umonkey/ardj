VERSION=1.0.2
ZIP=ardj-${VERSION}.zip
TAR=ardj-${VERSION}.tar.gz

build:
	@echo "This is a Python package, you don't need to build it.  Available commands:"
	@echo "make clean                     -- removes temporary files"
	@echo "make doc                       -- build the docbook"
	@echo "make install                   -- install using setup.py"
	@echo "make install [DESTDIR=./tmp]   -- install ardj"
	@echo "make package-ubuntu            -- create source and binary packages"
	@echo "make test                      -- runs unit tests"
	@echo "make test-syntax               -- runs unit tests"

test: test-syntax clean
	cp -f unittests/data/src/* unittests/data/
	rm -f tests.log tests-ardj.log
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml python unittests/all.py
	rm -f unittests/data/*.*

test-syntax:
	pep8 -r --ignore=E501 --exclude=twitter.py,socks.py,jabberbot.py src/ardj/*.py unittests/*.py

console:
	PYTHONPATH=src ./bin/ardj console $(MAIL)

install: ardj.html ardj.1.gz
	VERSION=$(VERSION) python setup.py install --root=$(DESTDIR)
	mkdir -p $(DESTDIR)/usr/bin
	mv $(DESTDIR)/usr/local/bin/ardj $(DESTDIR)/usr/bin/ardj
	rm -rf build

uninstall:
	cat install.log | xargs sudo rm -f

purge:
	sudo rm -rf /var/lib/ardj /var/log/ardj*

tar: clean
	mkdir ardj-$(VERSION)
	cp -R bin doc share src unittests packages/debian Makefile README.md TODO setup.py ardj-$(VERSION)/
	tar cfz $(TAR) ardj-$(VERSION)
	rm -rf ardj-$(VERSION)

package-debian: tar
	mkdir -p tmp
	cp $(TAR) tmp/ardj-$(VERSION).tar.gz
	cp $(TAR) tmp/ardj_$(VERSION).orig.tar.gz
	tar xfz ardj-$(VERSION).tar.gz --directory tmp
	cd tmp/ardj-$(VERSION) && debuild

release: clean bdist
	hg archive -t zip ${ZIP}
	googlecode_upload.py -s "ardj v${VERSION} (Source)" -p ardj -l Featured,Type-Source,OpSys-All ${ZIP}
	googlecode_upload.py -s "ardj v${VERSION} (Other)" -p ardj -l Featured,Type-Source,OpSys-All ${TAR}

clean:
	test -d .hg && hg clean || true
	rm -rf ardj.1.gz ardj.html doc/book.xml tmp
	find -regex '.*\.\(pyc\|rej\|orig\|zip\|tar\.gz\)$$' -print -delete

bdist: test clean ardj.1.gz ardj.html
	VERSION=$(VERSION) python setup.py bdist
	mv dist/*.tar.gz $(TAR)
	rm -rf build dist

zsh-completion: share/shell-extensions/zsh/_ardj

share/shell-extensions/zsh/_ardj: src/ardj/cli.py
	PYTHONPATH=src python bin/ardj --zsh > $@

serve:
	PYTHONPATH=$(pwd)/src ./bin/ardj serve

ardj.1.gz: share/doc/docbook/ardj.xml
	docbook2x-man share/doc/docbook/ardj.xml
	gzip -f9 ardj.1

ardj.html: ardj.1.gz
	man2html ardj.1.gz > ardj.html

man: ardj.html
	man ./ardj.1.gz

doc:
	make -C doc VERSION=$(VERSION)

.PHONY: doc clean package
