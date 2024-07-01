#!/usr/bin/env python3
'''
Created on 02.07.2015

@author: kraft-p
'''
import sys
import asyncio
import cherrypy

from trailer import system

from trailer.webapp import httpServer
from trailer.webapp.status import Root
from trailer.setup import setup


if __name__ == '__main__':


    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    # To understand the setup do not look at the code, look at preferences/sampler.config.yaml
    loop.run_until_complete(setup(system.trailer.devices))
    print('finished setup, got {} devices'.format(len(system.trailer.devices)))

    # system.progresscallbacks.idle = system.idleprogress

    # Try to load a schedule
    if len(sys.argv) > 1:
        system.trailer.loop.schedule.load(sys.argv[1])
        print('loaded schedule {}, pointer at: {}'.format(sys.argv[1], system.trailer.loop.schedule.sourcepointer))
    # system.loop.active = True


    page = Root(system.trailer)
    try:
        httpserver = httpServer(page, configfile='preferences/cherrypy.conf')
        print('Web server running, start main loop')

        loop.run_until_complete(system.trailer.main())

    finally:
        cherrypy.engine.exit()

