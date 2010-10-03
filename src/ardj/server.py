# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:
# http://fragments.turtlemeat.com/pythonwebserver.php

import logging
from xml.sax import saxutils
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

import config
import db

def quote(values, wrap=None):
	if type(values) != dict:
		raise Exception('quote() expects a dictionary.')
	xml = u''
	for k in values:
		if values[k] is not None:
			xml += u' ' + unicode(k) + u'=' + saxutils.quoteattr(unicode(values[k]))
	if wrap is not None:
		xml = u'<%s%s/>' % (wrap, xml)
	return xml

class ardj_server(BaseHTTPRequestHandler):
	def do_GET(self):
		if self.path == '/tracks':
			return self.do_get_tracks()

	def do_get_tracks(self):
		xml = u'<tracks>\n'
		for tr in db.track.get_all():
			xml += quote({
				'id': tr.id,
				'artist': tr.artist,
				'title': tr.title,
				'filename': tr.filename,
				'weight': tr.weight,
				'count': tr.count,
			}, wrap=u'track') + u'\n'
		xml += u'</tracks>\n'
		self.send_xml(xml)

	def send_xml(self, xml, status=200, content_type='text/plain'):
		self.send_response(status)
		self.send_header('Content-Type', content_type + '; charset=utf-8')
		self.end_headers()
		self.wfile.write('<?xml version="1.0"?>\n')
		self.wfile.write('<?xml-stylesheet type="text/xsl" href="/style.xsl"?>\n')
		if type(xml) == unicode:
			xml = xml.encode('utf-8')
		self.wfile.write(xml)

if __name__ == '__main__':
	try:
		port = config.get('server/port', 8765)
		server = HTTPServer(('', port), ardj_server)
		logging.info('Listening on port %u' % port)
		server.serve_forever()
	except KeyboardInterrupt:
		server.socket.close()
