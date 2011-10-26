VERSION=1.0.2
ARCH=`uname -m`
ZIP=ardj_${VERSION}.zip
TAR=ardj_${VERSION}.tar.gz

all: doc

help:
	@echo "bdist          -- prepares a tar.gz"
	@echo "clean          -- removes temporary files"
	@echo "install        -- install using setup.py"
	@echo "release        -- upload a new version to Google Code"
	@echo "test           -- runs unit tests"
	@echo "test-syntax    -- runs unit tests"
	@echo "uninstall      -- uninstall (installs first to find installed files)"
	@echo "doc            -- build the docbook"

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
	rm -rf build

uninstall:
	cat install.log | xargs sudo rm -f

purge:
	sudo rm -rf /var/lib/ardj /var/log/ardj*

release: clean bdist
	hg archive -t zip ${ZIP}
	googlecode_upload.py -s "ardj v${VERSION} (Source)" -p ardj -l Featured,Type-Source,OpSys-All ${ZIP}
	googlecode_upload.py -s "ardj v${VERSION} (Other)" -p ardj -l Featured,Type-Source,OpSys-All ${TAR}

clean:
	test -d .hg && hg clean || true
	rm -f ardj.1.gz ardj.html
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

docs:
	mkdir -p share/doc/ardj/pydoc
	rm -f share/doc/ardj/pydoc/*.html
	ls -1 src/ardj/*.py | grep -v __init__ | cut -d/ -f3 | cut -d. -f1 | sed -re 's/(.*)/ardj.\1/g' | xargs pydoc -w ardj
	mv *.html share/doc/ardj/pydoc/

ardj.1.gz: share/doc/docbook/ardj.xml
	docbook2x-man share/doc/docbook/ardj.xml
	gzip -f9 ardj.1

ardj.html: ardj.1.gz
	man2html ardj.1.gz > ardj.html
	cp ardj.html wiki/

man: ardj.html
	man ./ardj.1.gz

doc:
	make -C doc

.PHONY: doc clean
