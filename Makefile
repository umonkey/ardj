VERSION=1.0.16
TAR=ardj-${VERSION}.tar.gz
DEB=ardj_${VERSION}-1_all.deb
PYTHON=python

build:
	@echo "This is a Python package, you don't need to build it.  Available commands:"
	@echo "make clean                     -- removes temporary files"
	@echo "make doc                       -- build the docbook"
	@echo "make install                   -- install using setup.py"
	@echo "make install [DESTDIR=./tmp]   -- install ardj"
	@echo "make install-hooks             -- prepare the development environment"
	@echo "make package-ubuntu            -- create source and binary packages"
	@echo "make test                      -- runs unit tests"
	@echo "make test-syntax               -- runs PEP8 check"

test-units:
	cp -f unittests/data/src/* unittests/data/
	rm -f tests.log tests-ardj.log
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml $(PYTHON) unittests/all.py
	rm -f unittests/data/*.*

test-syntax:
	pep8 -r --ignore=E501 --exclude=twitter.py,socks.py,jabberbot.py src/ardj/*.py unittests/*.py

test: test-syntax test-units clean

console:
	PYTHONPATH=src ./bin/ardj console $(MAIL)

install: share/doc/man/ardj.1.gz
	VERSION=$(VERSION) $(PYTHON) setup.py install --root=$(DESTDIR)
	mkdir -p $(DESTDIR)/usr/bin
	mv $(DESTDIR)/usr/local/bin/ardj $(DESTDIR)/usr/bin/ardj
	rm -rf build

install-hooks:
	fgrep -q '[hooks]' .hg/hgrc || echo "\n[hooks]" >> .hg/hgrc
	fgrep -q 'pretxncommit' .hg/hgrc || echo "pretxncommit = python:src/hooks/hooks.py:check_commit_message" >> .hg/hgrc

uninstall:
	cat install.log | xargs sudo rm -f

purge:
	sudo rm -rf /var/lib/ardj /var/log/ardj*

tar: clean
	rm -rf ardj-$(VERSION)
	mkdir ardj-$(VERSION)
	cp -R bin doc share src unittests packages/debian Makefile README.md TODO setup.py ardj-$(VERSION)/
	tar cfz $(TAR) ardj-$(VERSION)
	rm -rf ardj-$(VERSION)

package-debian: tar
	rm -rf tmp; mkdir -p tmp
	cp $(TAR) tmp/ardj-$(VERSION).tar.gz
	cp $(TAR) tmp/ardj_$(VERSION).orig.tar.gz
	cp $(TAR) ardj_$(VERSION).orig.tar.gz
	tar xfz ardj-$(VERSION).tar.gz --directory tmp
	cd tmp/ardj-$(VERSION) && debuild -S
	mv tmp/ardj_$(VERSION)[_-]* ./
	rm -rf tmp

deb: tar
	rm -rf tmp; mkdir -p tmp
	cp $(TAR) tmp/ardj-$(VERSION).tar.gz
	cp $(TAR) tmp/ardj_$(VERSION).orig.tar.gz
	tar xfz ardj-$(VERSION).tar.gz --directory tmp
	cd tmp/ardj-$(VERSION) && debuild
	mv tmp/ardj_$(VERSION)[_-]* ./
	rm -rf tmp

depends-debian:
	sudo apt-get install devscripts

upload-ppa:
	dput ardj ardj_$(VERSION)-*.changes

release: doc man release-pypi

release-pypi:
	$(PYTHON) setup.py sdist upload

release-google:
	googlecode_upload.py -s "ardj v${VERSION} (Source)" -p ardj -l Featured,Type-Source,OpSys-All ${TAR}
	googlecode_upload.py -s "ardj v${VERSION} (Debian)" -p ardj -l Featured,Type-Source,OpSys-Debian ${DEB}

clean:
	rm -rf doc/book.xml share/doc/man/ardj.1.gz tests.log tmp
	find -regex '.*\.\(pyc\|rej\|orig\|zip\)$$' -delete

cleandist: clean
	rm -f ardj-* ardj_*

bdist: clean share/doc/man/ardj.1.gz
	VERSION=$(VERSION) $(PYTHON) setup.py bdist
	mv dist/*.tar.gz $(TAR)
	rm -rf build dist

sdist: clean share/doc/man/ardj.1.gz
	VERSION=$(VERSION) $(PYTHON) setup.py sdist

egg: clean share/doc/man/ardj.1.gz
	VERSION=$(VERSION) $(PYTHON) setup.py bdist_egg

zsh-completion: share/shell-extensions/zsh/_ardj

share/shell-extensions/zsh/_ardj: src/ardj/cli.py
	PYTHONPATH=src $(PYTHON) bin/ardj --zsh > $@

serve:
	PYTHONPATH=src ./bin/ardj serve

share/doc/man/ardj.1: src/docbook/man.xml
	docbook2x-man src/docbook/man.xml
	mkdir -p share/doc/man
	mv ardj.1 share/doc/man/ardj.1

share/doc/man/ardj.1.gz: share/doc/man/ardj.1
	gzip -f9 < share/doc/man/ardj.1 > share/doc/man/ardj.1.gz

man: share/doc/man/ardj.1.gz

doc:
	$(MAKE) -C doc VERSION=$(VERSION)

commit-doc: doc
	rm doc/book.xml
	hg add src/docbook
	hg commit src/docbook doc -l src/docbook/commit.txt
	hg push

pre-commit: zsh-completion

.PHONY: doc clean tar
