VERSION = 1.2.42
PYTHON = python3
DOCKER_IMAGE = ardj:latest
DOCKER_TAGS = 1.2.42 1.2 1 latest

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

autofix:
	autopep8 --in-place --aggressive -r bin src

bdist: setup.py
	$(PYTHON) setup.py bdist
	rm -rf src/ardj.egg-info setup.py
	ls -ldh dist/ardj-*.gz

build:
	docker build --tag $(DOCKER_IMAGE) --file build/Dockerfile .
	docker image prune -f

depends:
	python3 -m pip install -r requirements.txt

depends-dev:
	python3 -m pip install pylint autopep8 --upgrade

env:
	virtualenv env

lint:
	pylint bin src

push:
	for tag in $(DOCKER_TAGS); do \
		docker tag "$(DOCKER_IMAGE)" "umonkey/ardj:$$tag" ; \
		docker push "umonkey/ardj:$$tag" ; \
		docker rmi "umonkey/ardj:$$tag" ; \
	done

sdist: setup.py
	$(PYTHON) setup.py sdist
	rm -rf src/ardj.egg-info setup.py
	ls -ldh dist/ardj-*.gz

serve:
	docker run --rm --name ardj -p 8000:8000 -v $(PWD)/data:/app/data -e UID=$(shell id -u) -e GID=$(shell id -g) $(DOCKER_IMAGE)

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
	pep8 -r --ignore=E122,E124,E127,E128,E231,E501,E502 --exclude=twitter.py,socks.py,jabberbot.py src/ardj/*.py unittests/*.py

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

share/doc/man/ardj.1: src/docbook/man.xml
	docbook2x-man src/docbook/man.xml
	mkdir -p share/doc/man
	mv ardj.1 share/doc/man/ardj.1

share/doc/man/ardj.1.gz: share/doc/man/ardj.1
	gzip -f9 < share/doc/man/ardj.1 > share/doc/man/ardj.1.gz

man: share/doc/man/ardj.1.gz

doc:
	for fn in doc/*.md; do echo "Converting $$fn..."; pandoc -H doc/header.html -f markdown -t html --standalone $$fn -o share/doc/`basename $$fn .md`.html; done
	@#for fn in doc/*.md; do echo "Converting $$fn..."; pandoc -H doc/header.html -f markdown -t html --standalone $$fn -o static/doc/`basename $$fn .md`.html; done
	cp doc/screen.css share/doc/

doc_old: share/doc/html/index.html share/doc/html/ardj.html
	if [ -d $(HOME)/src/sites/umonkey.net/input/ardj/doc ]; then cp share/doc/html/* $(HOME)/src/sites/umonkey.net/input/ardj/doc; fi

share/doc/html/index.html: src/docbook/book.xml
	rm -f share/doc/html/*.html
	xsltproc --param use.id.as.filename 1 --stringparam html.stylesheet screen.css -o share/doc/html/ src/docbook/chunked-settings.xsl $<

share/doc/html/ardj.html: src/docbook/book.xml
	xsltproc --stringparam html.stylesheet screen.css -o $@ src/docbook/single-settings.xsl $<

src/docbook/book.xml: src/docbook/book.xml.in src/docbook/*.xml Makefile
	sed -e "s/@@VERSION@@/$(VERSION)/g" < $< | sed -e "s/@@DATE@@/`date +'%Y-%m-%d'`/g" > $@

pre-commit: zsh-completion

.PHONY: build clean doc depends
