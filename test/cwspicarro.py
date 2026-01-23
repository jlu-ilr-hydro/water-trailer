#!/usr/bin/python3

import sys
sys.path.append('.')
import yaml
import asyncio
import time
from trailer.devices import cwsclient, DeviceError
from trailer import get_config

async def showprogress(m, condition):
    while not condition():
        await m.cws.readstatus()
        print('{:40s}{:5.1%} {}'.format(str(m), m.progress, '*' * int(m.progress * 50)), end='\r')
        await asyncio.sleep(0.1)
    print('\nstop progress')

def ready_callback(m):
    print(time.ctime(),'Measurement {} is DONE!'.format(m))

    
async def test(c: cwsclient.CWSclient, sample=None, port=3):

    await c.readstatus()
    yaml.safe_dump(c.data, sys.stdout, default_flow_style=False)
    print()
    if sample=='stop':
        resp = await c.stopcws()
        print(resp)
        
    elif sample:
        m = await c.measure(sample, port, done_callback=ready_callback)
        print(m)
        print('\n', '*'*50)
        await c.readstatus()
        yaml.safe_dump(c.data, sys.stdout, default_flow_style=False)
        print()
        print('Wait for empty')
        await showprogress(m, m.can_empty.is_set)
        await m.can_empty.wait()
        print()
        print('Wait for ready')
        await showprogress(m, m.done)
        r = await m
        print(m)
        print(r)
   

if __name__ == '__main__':
    sample = sys.argv[1] if len(sys.argv)>1 else None
    try:
        port = int(sys.argv[2])
    except:
        port = 3
    conf = get_config()
    loop = asyncio.get_event_loop()
    loop.set_debug(1)
    
    c = loop.run_until_complete(cwsclient.create('cwspicarro', conf.devices.cwspicarro))
    loop.run_until_complete(test(c,sample,port))
