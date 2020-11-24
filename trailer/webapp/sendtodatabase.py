'''
Created on 08.02.2016

@author: kraft-p
'''


import cherrypy
import io
import requests

from . import postonly, mimetype, mime
from ..db.send import receive_update, collect_update, log_update, get_last_export_id
from .. import get_config, home

        
class Update:
    exposed=True
    @cherrypy.expose
    @mimetype(mime.html)
    def index(self):
        conf = get_config()
        print('\n'.join(conf.keys()))
        last_ids = get_last_export_id()
        last_text = '\n'.join('<li>{}: {}</li>'.format(k, v) for k, v in last_ids.items())
        return """
        <html>
            <head>
                <link href="/html/trailer.css" rel="stylesheet" type="text/css"/>
            </head>
            <body>
                <div class="normal">
                    <div class="fright big">
                        <a href="/loggerplot/" class="button" title="plot logger">&#x1f321;</a>
                        <a href="/wiki/" class="button" title="show wiki">?</a>
                        <a class="button" href="/" title="home">&#x2302;</a>
                    </div>
                    <h1>Update database</h1>
                    <ul>
                        <li>target: {url}</li>
                        {id_list}
                    </ul>
                </div>
            </body>
        </html>
        """.format(url=conf.mirror_db.url, id_list=last_text)

    @postonly
    @cherrypy.expose
    @mimetype(mime.plain)
    def receive(self):
        cl = cherrypy.request.headers['Content-Length']
        print('/update/receive: got {} bytes to update'.format(cl))
        rawbody = cherrypy.request.body.read(int(cl))
        (home / 'update.gz').write_bytes(rawbody)
        stream = io.BytesIO(rawbody)
        linecount = receive_update(stream, True)
        return str(linecount)

    @postonly
    @cherrypy.expose
    @mimetype(mime.plain)
    def send(self):
        conf = get_config()
        data, last_export_id, linecount = collect_update(verbose=True)
        r = requests.post(url=conf.mirror_db.url,
                          data=data)
        if int(r.text) == linecount:
            log_update(last_export_id)
        else:
            return 'Update was not succesful'




