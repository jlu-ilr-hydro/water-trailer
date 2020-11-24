'''
Created on 22.01.2016

@author: kraft-p
'''

from datetime import datetime
import cherrypy
from orderedattrdict import AttrDict

from . import mimetype, mime, postonly
from .. import db, home
from traceback import format_exc as traceback



class SchedulePage(object):
    
    exposed = True
    
    def __init__(self, schedule, system):
        self.schedule = schedule
        self.system = system

    @cherrypy.expose
    @mimetype(mime.html)
    def edit(self):
        """
        opens the schedule edit page
        """
        return (home / 'web/html/preferences.html').read_text()

    @cherrypy.expose
    @mimetype(mime.json)
    def index(self, nhist=5, nfuture=5):
        """
        Returns a json representation of the schedule
        with the following objects:

            - history: A list of nhist samples measured in the past
            - present: The current sample as given by system.current
            - future: A list of nfuture sources to be sampled in the future
        """
        offset = datetime.now() - datetime.utcnow()
        schedule = self.schedule
        with db.session_scope() as session:
            history = (session.query(db.Sample)
                       .order_by(db.Sample.time.desc())  # @UndefinedVariable
                       .limit(int(nhist)).all())
            history.reverse()
            future_id = []
            future_time = []
            for fid, ft in schedule.future(int(nfuture)):
                future_id.append(fid)
                future_time.append(ft)
            if future_id:
                future = session.query(db.Source).filter(
                    db.Source.id.in_(future_id))
                fdict = dict((so.id, so) for so in future)

                l = []
                for s_id, t in zip(future_id, future_time):
                    tstr = (t + offset).strftime('%Y-%m-%d %H:%M:%S')
                    s = fdict[s_id].to_json()
                    s.due = tstr
                    l.append(s)

                fjson = db.as_json(l)
            else:
                fjson = '[]'
            
            curr = None
            if schedule.currentsource:
                currsource = session.query(db.Source).get(schedule.currentsource)
                curr = currsource.to_json()

            hjson = db.as_json([s.to_json(True) for s in history])
            cjson = db.as_json(curr)
            
        return ('{"name":"' + str(schedule) + '"' +
                ',"history":' + hjson +
                ',"future":' + fjson +
                ',"current":' + cjson +
                ',"pointer":' + str(schedule.sourcepointer) +
                '}')

    def itervalveids(self):
        """
        Iterates through the valve id's
        """
        try:
            vs = self.system.devices.valvesystem
            for vid in vs.itervalveids():
                yield vid
        except AttributeError:
            for i in range(12):
                yield i+1

    def sources(self, session):
        """
        Returns a dict describing the schedule settings
        """
        res = AttrDict()
        # Get all potential sources
        sources = (session.query(db.Source)
                   .filter(db.Source.valveid > 0)
                   .order_by(db.Source.valveid)
                   ).all()

        sdict = AttrDict((so.id, so.to_json()) for so in sources)

        res.time_per_source = self.schedule.time_per_source

        res.schedule = [sdict[so]
                        for so in self.schedule.sourcequeue
                        if so in sdict
                        ]
        res.events = []
        for ev in self.schedule.events:
            entry = AttrDict(condition=ev.condition,
                             blocktime=ev.blocktime)

            try:
                entry.sources = [sdict[s] for s in ev.tag if s in sdict]
            except TypeError:
                entry.sources = [sdict[s] for s in [ev.tag] if s in sdict]
            res.events.append(entry)

        res.sources = [so.to_json() for so in sources if so.id in sdict]

        return res


    @cherrypy.expose
    @mimetype(mime.json)
    def sources_json(self):
        """
        Returns a complex description of the schedule as json:
         - schedule: list of sources in regular schedule
         - events: event based sources
         - unused: sources not in the schedule
         - freevalves: list of valveids not connected to source
         - schedulenames: list of saved schedule names
        """
        with db.session_scope() as session:
            sources = self.sources(session)
        sources['name'] = self.schedule.name
        # Get list of sources in schedule
        usedvalves = set(so['valveid']
                         for so in (sources.schedule + sources.sources))
        freevalves = sorted(set(self.itervalveids()) - usedvalves)
        sources['freevalves'] = freevalves
        schedulenames = self.schedule.listdir()
        sources['schedulenames'] = schedulenames
        sources['time_per_source'] = self.schedule.time_per_source / 60.
        return db.as_json(sources)
    
    @cherrypy.expose
    @postonly
    @cherrypy.tools.json_in()
    def load(self, **kwargs):
        name = cherrypy.request.json.get('name')
        if not name:
            return self.clear()
        try:
            self.schedule.load(name)
        except:
            return traceback()

    @cherrypy.expose
    @postonly
    @cherrypy.tools.json_in()
    def kill(self, **kwargs):
        name = cherrypy.request.json.get('name')
        if not name:
            return self.clear()
        try:
            self.schedule.killfile(name)
        except:
            return traceback()

    @cherrypy.expose
    @postonly
    def clear(self, **kwargs):
        try:
            self.schedule.clear()
        except:
            return traceback()
    
    @cherrypy.expose
    @postonly
    @cherrypy.tools.json_in()
    def write(self, **kwargs):
        """
        Saves the schedule as submitted as json
        """
        try:
            newschedule = cherrypy.request.json
            self.schedule.name = newschedule.pop('schedulename', 'default')
            self.schedule.update(newschedule)
            self.schedule.save(self.schedule.name)
        except:
            return traceback()
    
    @cherrypy.expose
    @postonly
    def injectsource(self, sourceid):
        self.schedule.inject_once(int(sourceid))

    @cherrypy.expose
    @postonly
    def skip_next(self):
        self.schedule.skip_next()

