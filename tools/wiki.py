#!/usr/bin/env python3

"""
Serves the wikipage only
"""

from trailer.webapp import httpServer
from trailer.webapp.wiki import WikiPage, home
from trailer.webapp.plot import LoggerPlot, SamplePlot, Map
from trailer.webapp.sendtodatabase import Update
import time
from cherrypy import expose, engine

class Root:
    exposed = True
    wiki = WikiPage()
    loggerplot = LoggerPlot()
    plot = SamplePlot()
    map = Map()
    update = Update()
    @expose
    def index(self):
        return """
        <html>
            <head>
                <link href="/html/trailer.css" rel="stylesheet" type="text/css"/>
            </head>
            <body>
                <div class="normal">
                    <h1><a class="button" href="/wiki">wiki</a></h1>
                    <h1><a class="button" href="/loggerplot">logger plot</a></h1>
                    <h1><a class="button" href="/plot">sampler plot</a></h1>
                    <h1><a class="button" href="/map">map</a></h1>
                </div>
            </body>
        </html>
        """

if __name__ == '__main__':
    print('WIKIHOME=', home)
    root = WikiPage()
    server = httpServer(root=Root(), configfile='preferences/cherrypy.conf', port=10081)
    try:
        while True:
            print('Webserver running on 10081')
            if input('Write q [Enter] to quit: ')=='q':
                break
    finally:
        engine.exit()

