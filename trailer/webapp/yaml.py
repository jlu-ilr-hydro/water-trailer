import cherrypy
import datetime
import time

from orderedattrdict import AttrDict

from . import mimetype, mime
from .. import db, home
from ..logger.db import LoggerSource, LoggerValue


def html(obj):
    if hasattr(obj, '__html__'):
        return obj.__html__()
    else:
        return str(obj)


class Yamledit(object):
    exposed = True

    @cherrypy.expose
    def index(self):
        return (home / 'web/html/yaml.html').read_text(encoding='utf-8')

