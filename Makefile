VERSION=1.0.16
PYTHON=python

help:
	@echo "make build                     -- prepare generated files"
	@echo "make clean                     -- removes temporary files"
	@echo "make doc                       -- build the docbook"
	@echo "make install                   -- install ardj using pip"
	@echo "make install-hg-hooks          -- prepare the development environment"
	@echo "make package-ubuntu            -- create source and binary packages"
	@echo "make release                   -- upload a new version to PYPI"
	@echo "make test                      -- runs unit tests"
	@echo "make test-syntax               -- runs PEP8 check"
	@echo "make uninstall                 -- uninstall ardj using pip"

build: test doc man setup.py

setup.py: setup.py.in Makefile
	sed -e "s/@@VERSION@@/$(VERSION)/g" < $< > $@

test: test-syntax test-units

test-units:
	cp -f unittests/data/src/* unittests/data/
	rm -f tests.log tests-ardj.log
	PYTHONPATH=src ARDJ_SETTINGS=unittests/data/settings.yaml $(PYTHON) unittests/all.py
	rm -f unittests/data/*.*

test-syntax:
	pep8 -r --ignore=E501 --exclude=twitter.py,socks.py,jabberbot.py src/ardj/*.py unittests/*.py

install: build
	$(PYTHON) setup.py sdist
	sudo pip install dist/ardj-$(VERSION).tar.gz --upgrade

uninstall:
	sudo pip uninstall ardj

install-hg-hooks:
	fgrep -q '[hooks]' .hg/hgrc || echo "\n[hooks]" >> .hg/hgrc
	fgrep -q 'pretxncommit' .hg/hgrc || echo "pretxncommit = python:src/hooks/hooks.py:check_commit_message" >> .hg/hgrc

release: build release-pypi

release-pypi:
	$(PYTHON) setup.py sdist upload

release-google: build
	$(PYTHON) setup.py sdist
	googlecode_upload.py -s "ardj v${VERSION} (Source)" -p ardj -l Featured,Type-Source,OpSys-All dist/ardj-$(VERSION).tar.gz

clean:
	rm -rf doc/book.xml share/doc/man/ardj.1.gz tests.log tmp
	find -regex '.*\.\(pyc\|rej\|orig\|zip\)$$' -delete
	rm -f ardj-* ardj_*

egg: build
	$(PYTHON) setup.py bdist_egg

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

.PHONY: doc clean
