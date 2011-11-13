#!/usr/bin/python
# -*- coding: utf-8 -*-

from jinja2 import Environment, PackageLoader
default_mimetype = 'text/html'
env = Environment(loader=PackageLoader('render', ''))

def render_to_response(filename, context={}, mimetype=default_mimetype):
    for key in context.keys():
        try: context[key] = context[key].decode('utf-8')
        except: pass
    template = env.get_template(filename)
    rendered = template.render(**context)
    return rendered
