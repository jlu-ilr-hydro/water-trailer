#!/usr/bin/python3
'''
Created on 30.03.2016

@author: kraft-p
'''
import asyncio
import time
import sys
import yaml
from trailer.logger.bus import Bus

async def test(cc: Bus):
    print('get values')
    tstart = time.time()

    res = await cc.read_all()
    print(yaml.dump(res, default_flow_style=False))
    print('{:.3}s'.format(time.time()-tstart))


if __name__ == '__main__':
    cc = Bus.from_file('preferences/colorcontrol.bus.yaml')

    loop = asyncio.get_event_loop()
    loop.set_debug(1)
    loop.run_until_complete(test(cc))


    # open(__file__,'a').write('# {} successful on {}\n'.format(' '.join(sys.argv),time.ctime()))

