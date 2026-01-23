#!/usr/bin/python3
'''
Test the functionality of the ioalpha module


Created on 26.04.2016

@author: kraft-p
'''
import sys
import asyncio
import yaml
sys.path.append('.')
from trailer.devices import ioalpha
from trailer import address
async def test(port):
    print('Create IO-\u03b1...')
    dev = await ioalpha.create(port, 1.0)
    dev.addscale(1, 'test AI', 10.0, 5.0)
    print('Read status')
    await dev.readstatus()
    yaml.dump(dev.data, default_flow_style=False)
    print('Make a relay on O1')
    R1 = dev.makerelay(1)
    print('Open relay on O1')    
    await R1(True)
    yaml.dump(dev.data, default_flow_style=False)
    assert await R1.is_open(), 'R1 is not open'
    print('set target temp to 5.0degC')
    await dev.settemp(5.0)
    await dev.readstatus()
    yaml.dump(dev.data, default_flow_style=False)
    assert (dev.data['targettemp'] - 5.0)**2 < 0.1**2, 'Target temp not at 5.0 degC but {}'
    print('wait 5.0')
    await asyncio.sleep(5.0)
    print('Stop relay')
    await R1(False)
    yaml.dump(dev.data, default_flow_style=False)
    assert not (await R1.is_open()), 'R1 is not closed'
    print('start heating')
    await dev.toggleheat()
    await dev.readstatus()
    yaml.dump(dev.data, default_flow_style=False)
    print('wait 5.0')
    await asyncio.sleep(5.0)
    print('stop heat')
    await dev.toggleheat()
    await dev.readstatus()
    
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test(address.alphaIO))
