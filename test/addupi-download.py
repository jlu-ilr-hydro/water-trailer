#!/usr/bin/python3
"""
Downloads data from the adcon system since a given date
"""

import sys
from trailer.logger.bus import Bus
from datetime import timedelta, datetime
from trailer.logger.csvlogger import Csv
import asyncio

async def waitfor(coro):
    """
    Starts a coroutine and shows some animated cursor during the waiting phase
    """
    T = asyncio.ensure_future(coro)
    while not T.done():
        for c in '-\|/':
            print(c, end='\r')
            await asyncio.sleep(0.1)
    print('done')
    return T.result()
    
def await(coro):
    """ 
    Starts a coroutine in the standard loop and animates  a cursor
    """
    return asyncio.get_event_loop().run_until_complete(waitfor(coro))

if __name__ == '__main__':
    # Check the commandline syntax for number of entries
    if len(sys.argv)<4:
        print('Usage: test/addupi-download.py [bus.yaml] [output.csv] [startdate yyyymmdd-hhmm]')
        exit()
        
    # Create a bus from the bus description
    bus = Bus.from_file(sys.argv[1])
    csv = Csv(sys.argv[2],'a')
    try:
        end = datetime.strptime(sys.argv[3], '%Y%m%d-%H%M')
    except ValueError:
        print('Wrong date format: {} does not match yyyymmdd-hhmm. 20160901-1340 would work')
        exit()
    for sensor in bus.sensors:
        print('Read sensor:', sensor)
        res = await(bus.readsensor(sensor, fromdate=end, slots=100000))
        print('...got {} values'.format(len(res)))
        csv(res)
    csv.close()
