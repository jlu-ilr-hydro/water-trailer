#!/usr/bin/python3

'''
Created on 30.03.2016

@author: kraft-p
'''

import asyncio
import time
import sys
import yaml

from trailer.devices import tribox
from trailer import address, get_config
tribox.debug = True

def yprint(data):
    yaml.dump(dict(data), sys.stdout, default_flow_style=False)

async def test(measure):
    print('create tribox')
    conf = get_config()
    tb = await tribox.create('tribox', conf.devices.tribox)

    print('get names:')
    for dev in tb.tribox, tb.props, tb.lsa:
        print(dev.unit, await dev.fixed_name())

    print('read status')
    await tb.readstatus()

    yprint(tb.data)

    if not measure:
        return
    tb.is_ready.clear()
    T = asyncio.ensure_future(tb.measure())
    tstart = time.time()
    print('wait for result')
    while not tb.is_ready.is_set():
        await asyncio.sleep(0.5)
        print('wait {:0.1f}s for result'.format(time.time() - tstart), end='\n')
        await tb.readstatus()
    await T
    
    yprint(tb.data)

if __name__ == '__main__':  
    loop = asyncio.get_event_loop()
    loop.set_debug(1)

    loop.run_until_complete(test('m' in sys.argv))
