'''
Created on 02.07.2015

@author: kraft-p
'''

import cherrypy
from orderedattrdict import AttrDict
from . import mimetype, mime
from . import wiki
from .. import db, home
from .source import SourcePage
from .schedule import SchedulePage
from . import plot
import datetime
import time
import io
from trailer.webapp.yamleditor import Yamledit
from trailer import CodeTimer

postonly = cherrypy.tools.allow(methods=['POST'])  # @UndefinedVariable




        
class Tools:
    exposed = True

    def __init__(self, system):
        self.system = system
        
    @cherrypy.expose
    @postonly
    def calibratescale(self, currentvol=0.5):
        if self.system.valvesystem:
            self.system.valvesystem.calibrate(currentvol)


    @cherrypy.expose
    @postonly
    def devices_toggle_active(self, devicename):
        """
        Called by url /tools/devives.toggle.active/cwspicarro
        :param devicename: The name of the device
        :return: Empty string on success, error message on error
        """
        try:
            dev = self.system.devices[devicename]
            dev.active = not dev.active
        except KeyError:
            return 'Device "{}" not in system'.format(devicename)
        except AttributeError:
            return 'Device "{}" has not an active flag'.format(devicename)
        except Exception as e:
            return 'Toggle active state of "{}" raised {!r}'.format(devicename, e)
        else:
            return ''

class Root:
    
    def __init__(self, system):
        self.system = system
        self.source = SourcePage()
        self.schedule = SchedulePage(system.loop.schedule, system)
        self.plot = plot.SamplePlot()
        self.loggerplot = plot.LoggerPlot()
        self.yamleditor = Yamledit()
        self.tools = Tools(system)
        self.wiki = wiki.WikiPage()
        self.map = plot.Map()

    @cherrypy.expose
    @mimetype(mime.html)
    def index(self):
        """
        Shows the status page
        """
        return (home / 'web/html/status.html').read_text()

    @cherrypy.expose
    @mimetype(mime.html)
    def mobile(self):
        return (home / 'web/html/mstatus.html').read_text()

    @cherrypy.expose
    @mimetype(mime.json)
    def status(self, **kwargs):
        """
        Returns the json representation of the system
        including all device values
        """
        print('Timing status.py')
        ct = CodeTimer()
        data = self.system.to_json()
        data.current.active = self.system.loop.active
        ct('system-data')
        if 'loglevel' in kwargs:
            with db.session_scope() as session:
                level = int(kwargs['loglevel'])
                count = int(kwargs.get('logcount', 20))
                data['logbook'] = db.readlog(session, level, count)
        ct('log-data')
        ssys = db.as_json(data)
        ct('system-data2json')
        ssch = self.schedule.index(nhist=int(kwargs.get('nhist', 5)),
                                   nfuture=int(kwargs.get('nfuture', 5)))
        print(ct('schedule-json'))
        return "[" + ssys + "," + ssch.decode() + "]"

    @cherrypy.expose
    @mimetype(mime.json)
    def log(self, loglevel='5', logcount='50'):
        with db.session_scope() as session:
            level = int(loglevel)
            count = int(logcount)
            return db.as_json(db.readlog(session, level, count))

    @cherrypy.expose
    @postonly
    @mimetype(mime.plain)
    def setactive(self, value):
        """
        Toggles the active state of the schedule
        """
        self.system.loop.active = value == 'true'

    @cherrypy.expose
    @mimetype(mime.html)
    def sample(self, sampleid):
        id = int(sampleid)
        valstr = io.StringIO()
        with db.session_scope() as session:
            sample = session.query(db.Sample).get(id)
            valstr.write('<h2>{}</h2>\n'.format(sample))
            template="""
            <div class="normal">
                <span class="key">{value.valuetype.name_html}</span>
                <span class="value">{value.value:0.4g}{value.valuetype.unit_html}</span>
            </div>
            """
            valstr.write('<h3>Values</h3>\n')
            for value in sample.values:
                valstr.write(template.format(value=value))
        return (home / 'web/html/sample.html').read_text().format(values=valstr.getvalue(),id=id)
        
        
    @cherrypy.expose
    @postonly
    @mimetype(mime.plain)
    def shutdown_server(self):
        self.system.shutdown_threadsafe()
        return "Server is going offline"
               

    
    @cherrypy.expose
    @mimetype(mime.html)
    def rack(self):
        from ..devices.robotaio import FridgeRack
        rack = FridgeRack().getfilled()
        out = io.StringIO()
        for rcs in rack:
            out.write('<div class="level">')
            for cs in rcs:
                out.write('  <div class="row">')
                for sample in cs:
                    out.write('    <div class="bottle {}">'.format('full' if sample else 'empty'))
                    if sample:
                        out.write('      <a href="sample/{0}">#{0}</a>'.format(sample))
                    out.write('    </div>')
                out.write('  </div>')
            out.write('</div>')
        html = (home / 'web/html/rack.html').read_text()
        
        return html.replace('<!--BOTTLES-->', out.getvalue())
