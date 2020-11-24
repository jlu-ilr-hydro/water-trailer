import cherrypy
from .. import db

postonly = cherrypy.tools.allow(methods=['POST'])  # @UndefinedVariable


class SourcePage(object):
    """
    Handles request changing source properties
    URL-Schema is: /source/action
    """

    exposed = True

    @cherrypy.expose
    @postonly
    def add(self, valveid, name):
        """
        Adds a source to the list of sources.
        """
        try:
            valveid = int(valveid)
        except (ValueError, TypeError) as err:
            return "{} is not a valve identifier".format(valveid)

        try:
            with db.session_scope() as session:
                q = session.query(db.Source).filter_by(valveid=int(valveid))

                if q.count():
                    return ("{} is already connected to V{}"
                            .format(q.first(), valveid))

                newsource = db.Source(valveid=int(valveid), name=name)
                session.add(newsource)
        except Exception as err:
            return str(err)

    @cherrypy.expose
    @postonly
    def unlink(self, valveid):
        """
        Removes a source from a valveid. Reconnection should never occur.
        """
        try:
            valveid = int(valveid)
        except (ValueError, TypeError):
            return "{} is not a valve identifier".format(valveid)

        with db.session_scope() as session:
            (session.query(db.Source)
             .filter_by(valveid=valveid)
             .update({'valveid': None}))

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @postonly
    def change(self):
        """
        Changes the properties of the source, given as
        a json data
        """
        kwargs = cherrypy.request.json
        if 'id' not in kwargs:
            return "The id of the source is not given"

        with db.session_scope() as session:
            source = session.query(db.Source).get(int(kwargs['id']))
            # For each property in the posted json
            for attr in kwargs:
                if hasattr(source, attr):
                    setattr(source, attr, kwargs[attr])

