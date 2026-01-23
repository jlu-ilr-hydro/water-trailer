
import cherrypy
import threading

from .. import home
web = (home / 'web').resolve()

postonly = cherrypy.tools.allow(methods=['POST'])  # @UndefinedVariable


class httpServer(threading.Thread):
    """The cherrypy quickstart server in a seperate thread. You can kill the thread
    but not stop it.
    """

    def run(self):
        self.server = cherrypy.quickstart(root=self.root, config=self.config)
        print("Server is gone")

    def read_config(self, fn):
        """
        Reads a config file
        :param fn:
        :return:
        """

        fn = (home / fn).resolve()
        conftxt = fn.read_text()
        conftxt = conftxt.replace('$HOME', str(web.resolve().as_posix()) )
        conf = eval(conftxt)
        return conf

    def __init__(self, root, config=None, configfile=None, port=None):
        super().__init__()
        self.server = None
        self.root = root
        config = config or {}
        cherrypy.server.socket_host = "0.0.0.0"
        cherrypy.server.socket_port = port or 20080
        cherrypy.config.update({
            "engine.autoreload.on": False,
            "tools.encode.encoding": "utf-8",
            "tools.encode.on": True,
            "tools.encode.decode": True,
            "log.screen": False,
            "log.access_file": (web / 'log/access.log').as_posix(),
            "log.error_file": (web / 'log/error.log').as_posix()
        })
        if configfile:
            config.update(self.read_config(configfile))
        self.config = config
        self.daemon = True
        self.start()


class mime:
    json = 'application/json'
    plain = 'text/plain'
    xml = 'text/xml'
    html = 'text/html'
    jpeg = 'image/jpeg'
    png = 'image/png'
    csv = 'text/csv'
    pdf = 'application/pdf'
    js = 'text/javascript'


def html(obj):
    if hasattr(obj, '__html__'):
        return obj.__html__()
    else:
        return str(obj)


def mimetype(mtype):
    def decorate(func):
        def wrapper(*args, **kwargs):
            cherrypy.response.headers['Content-Type'] = mtype
            if mtype in [mime.json]:
                return bytes(func(*args, **kwargs),
                             encoding=cherrypy.config['tools.encode.encoding'])
            else:
                return func(*args, **kwargs)
        return wrapper
    return decorate
