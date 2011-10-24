all: single/index.html chunked/index.html

single/index.html: ../src/docbook/book.xml Makefile ../Makefile
	xsltproc --stringparam html.stylesheet screen.css -o single/index.html single/settings.xsl ../src/docbook/book.xml

chunked/index.html: ../src/docbook/book.xml Makefile ../Makefile
	rm -f chunked/*.html
	xsltproc --param use.id.as.filename 1 --param chunker.output.encoding UTF-8 --stringparam html.stylesheet screen.css -o chunked/ /usr/share/xml/docbook/stylesheet/docbook-xsl/html/chunk.xsl ../src/docbook/book.xml
