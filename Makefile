VERSION=1.2.23
PYTHON=python

help:
	@echo "make build                     -- prepare generated files"
	@echo "make clean                     -- removes temporary files"
	@echo "make doc                       -- build the docbook"
	@echo "make env                       -- set up VirtualEnv"
	@echo "make install                   -- install ardj using pip"
	@echo "make install-hg-hooks          -- prepare the development environment"
	@echo "make package-ubuntu            -- create source and binary packages"
	@echo "make release                   -- upload a new version to PYPI"
	@echo "make test                      -- runs unit tests"
	@echo "make test-syntax               -- runs PEP8 check"
	@echo "make uninstall                 -- uninstall ardj using pip"

bdist: setup.py
	$(PYTHON) setup.py bdist
	rm -rf src/ardj.egg-info setup.py
	ls -ldh dist/ardj-*.gz

build: test doc man setup.py

env:
	virtualenv env

sdist: setup.py
	$(PYTHON) setup.py sdist
	rm -rf src/ardj.egg-info setup.py
	ls -ldh dist/ardj-*.gz

setup.py: setup.py.in Makefile
	sed -e "s/@@VERSION@@/$(VERSION)/g" < $< > $@
	chmod a+x setup.py

test: test-syntax test-units

test-units:
	cp -f unittests/data/src/* unittests/data/
	rm -f tests.log tests-ardj.log
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml ARDJ_CONFIG_DIR=unittests/data $(PYTHON) unittests/all.py
	rm -f unittests/data/*.*

test-syntax:
	pep8 -r --ignore=E501 --exclude=twitter.py,socks.py,jabberbot.py src/ardj/*.py unittests/*.py

install:
	$(PYTHON) setup.py sdist
	rm -f setup.py
	sudo pip install --upgrade dist/ardj-$(VERSION).tar.gz

uninstall:
	sudo pip uninstall ardj

install-hg-hooks:
	fgrep -q '[hooks]' .hg/hgrc || echo "\n[hooks]" >> .hg/hgrc
	fgrep -q 'pretxncommit' .hg/hgrc || echo "pretxncommit = python:src/hooks/hooks.py:check_commit_message" >> .hg/hgrc

release: release-pypi

release-pypi: build
	$(PYTHON) setup.py sdist upload --sign
	rm -rf setup.py src/ardj.egg-info

clean:
	rm -rf src/docbook/book.xml setup.py MANIFEST share/doc/man/ardj.1.gz tests.log tmp
	find -regex '.*\.\(pyc\|rej\|orig\|zip\)$$' -delete
	rm -f ardj-* ardj_*

egg: build
	$(PYTHON) setup.py bdist_egg
	rm -f setup.py

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

doc: share/doc/html/index.html share/doc/html/ardj.html
	if [ -d $(HOME)/src/sites/umonkey.net/input/ardj/doc ]; then cp share/doc/html/* $(HOME)/src/sites/umonkey.net/input/ardj/doc; fi

share/doc/html/index.html: src/docbook/book.xml
	rm -f share/doc/html/*.html
	xsltproc --param use.id.as.filename 1 --stringparam html.stylesheet screen.css -o share/doc/html/ src/docbook/chunked-settings.xsl $<

share/doc/html/ardj.html: src/docbook/book.xml
	xsltproc --stringparam html.stylesheet screen.css -o $@ src/docbook/single-settings.xsl $<

src/docbook/book.xml: src/docbook/book.xml.in src/docbook/*.xml Makefile
	sed -e "s/@@VERSION@@/$(VERSION)/g" < $< | sed -e "s/@@DATE@@/`date +'%Y-%m-%d'`/g" > $@

pre-commit: zsh-completion

.PHONY: doc clean
