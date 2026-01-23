import cherrypy
import datetime
import time

from attrdictionary import AttrDict

from . import mimetype, mime
from .. import db, home
from ..logger.db import LoggerSource, LoggerValue


def html(obj):
    if hasattr(obj, '__html__'):
        return obj.__html__()
    else:
        return str(obj)

class Plot(object):
    exposed = True

    @cherrypy.expose
    def index(self):
        return (home / 'web/html/plot.html').read_text(encoding='utf-8')



class SamplePlot(Plot):
    @cherrypy.expose
    @mimetype(mime.json)
    def valuetypes(self, **kwargs):
        with db.session_scope() as session:
            return db.as_json(AttrDict((vt.name, vt.to_json())
                                   for vt in session.query(db.ValueType)))

    @cherrypy.expose
    @mimetype(mime.json)
    def amilogger(self, **kwargs):
        return db.as_json(False)

    @cherrypy.expose
    @mimetype(mime.json)
    def data(self, valuetype, **kwargs):
        """
        Returns data for the sample history plot as json
        data : dictionary of source ids to list of time/value tuples for flot.
                Time is in milliseconds since epoch
        sources: dictionary with sources by id
        """
        days = float(kwargs.pop('days', 7))
        options = {'start': int((time.time() - days * 86400) * 1000),
                   'end': int((time.time() * 1000)),
                   }

        with db.session_scope() as session:
            begin = datetime.datetime.utcfromtimestamp(int(options['start']) / 1000.)
            end = datetime.datetime.utcfromtimestamp(int(options['end']) / 1000.)
            samples = (session.query(db.Sample)
                       .filter(db.Sample.time >= begin)
                       .filter(db.Sample.time <= end)
                       .order_by(db.Sample._source, db.Sample.time)
                       )
            data = {}
            for sample in samples:
                value = sample.valuedict().get(valuetype)
                if sample.source.name in data:
                    data[sample.source.name]['data'].append((int(sample.gettimestamp() * 1000),
                                                             value))
                else:
                    data[sample.source.name] = {'label': sample.source.name,
                                                'data': [(int(sample.gettimestamp() * 1000), value)]
                                                }

            return db.as_json(data)


class LoggerPlot(Plot):
    @cherrypy.expose
    @mimetype(mime.json)
    def valuetypes(self, **kwargs):
        with db.session_scope() as session:
            return db.as_json(AttrDict((vt.name, vt.to_json())
                                       for vt in session.query(LoggerSource)))

    @cherrypy.expose
    @mimetype(mime.json)
    def amilogger(self, **kwargs):
        return db.as_json(True)


    @cherrypy.expose
    @mimetype(mime.json)
    def data(self, valuetype, **kwargs):
        """
        Returns data for the sample history plot as json
        data : dictionary of source ids to list of time/value tuples for flot.
                Time is in milliseconds since epoch
        sources: dictionary with sources by id
        """
        days = float(kwargs.pop('days', 7))
        options = {'start': int((time.time() - days * 86400) * 1000),
                   'end': int((time.time() * 1000)),
                   }

        with db.session_scope() as session:
            # Get LoggerSource from valuetype
            ls = session.query(LoggerSource).filter_by(name=valuetype).first()
            # Get time frame
            begin = datetime.datetime.utcfromtimestamp(int(options['start']) / 1000.)
            end = datetime.datetime.utcfromtimestamp(int(options['end']) / 1000.)
            values = (session.query(LoggerValue)
                       .filter(LoggerValue.time >= begin)
                       .filter(LoggerValue.time <= end)
                       .filter_by(source_id=ls.id)
                       .order_by(LoggerValue.time)
                       )
            data = AttrDict()
            data.logger = AttrDict({'label': html(ls)})
            data.logger.data = [(int(v.gettimestamp() * 1000), v.value)
                                for v in values]

            return db.as_json(data)

class Map:
    @cherrypy.expose
    def index(self):
        lat_id = 32
        lon_id = 33
        with db.session_scope() as session:
            values = (session.query(LoggerValue)
                      .filter(LoggerValue.source_id.in_([lat_id, lon_id]))
                      .order_by(LoggerValue.time.desc(), LoggerValue.source_id)
                      .limit(2)
                       )
            lat, lon = [v.value for v in values]
            text = (home / 'web/html/map.html').read_text(encoding='utf-8')
            return text.format(lat=lat, lon=lon)
