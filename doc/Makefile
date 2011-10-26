VERSION=0.0
DATE=`date +'%Y-%m-%d'`

all: single/index.html chunked/index.html

book.xml: ../src/docbook/book.xml Makefile ../Makefile
	cat ../src/docbook/book.xml \
	| sed -e "s/VERSION_NUMBER/$(VERSION)/g" \
	| sed -e "s/RELEASE_DATE/$(DATE)/g" \
	> book.xml

single/index.html: book.xml
	xsltproc --stringparam html.stylesheet screen.css -o single/index.html single/settings.xsl book.xml

chunked/index.html: book.xml
	rm -f chunked/*.html
	xsltproc --param use.id.as.filename 1 --param chunker.output.encoding UTF-8 --stringparam html.stylesheet screen.css -o chunked/ /usr/share/xml/docbook/stylesheet/docbook-xsl/html/chunk.xsl book.xml
