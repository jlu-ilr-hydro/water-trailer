#!/usr/bin/env python3
import asyncio


from trailer import get_config
from trailer.logger.bus import Bus
from trailer.logger.schedule import Schedule
from trailer.logger.jsonserver import ServeLog


if __name__ == '__main__':
    conf = get_config()
    conf = conf.devices.logger
    loop = asyncio.get_event_loop()
    busses = []
    t = conf.readraster

    for fn in conf.busses:
        try:
            bus = Bus.from_file('preferences/' + fn + '.bus.yaml')
        except FileNotFoundError:
            print('{} not found, skipping'.format(fn))
        except Exception as e:
            print('{} not loaded as bus. Error:')
            print(e)
        else:
            busses.append(bus)

    if not busses:
        print('No Bus available')
    else:
        print('\nBusses:\n','=' * 10)
        for bus in busses:
            print(bus)
        print()
        server = ServeLog(port=conf.port, outfile=conf.outfile, serve_all=True)
        # server.verbose = True
        loop.run_until_complete(server.open())
        server.schedule = Schedule(t, busses, onread=server.update)
        loop.run_until_complete(server.closed.wait())


