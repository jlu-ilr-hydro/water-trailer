#!/usr/bin/python3
'''
Created on 07.04.2016

@author: kraft-p
'''

import asyncio
import sys
import time
import yaml

from trailer.devices import wago_valvesystem, ysi600r
from trailer import get_config
single_measures = 1
ysi600r.debug = 1

stop = asyncio.Event()
async def showprogress(dev):
    """
    Function to show progress of a device
    """
    loop = asyncio.get_event_loop()
    tstart = loop.time()
    dev.is_ready.clear()
    while not dev.is_ready.is_set():
        await dev.readstatus()
        p = dev.progress()
        print('{:5.1f}s {:5.1%}{}'.format(loop.time()-tstart, p, '*' * int(p*50)), end='\r')
        await asyncio.sleep(0.1)
    print()
    return await dev.readstatus()

async def pwait(coro, dev):
    """
    Wrapper coroutine to start coro and show progress of dev
    :param coro: a coroutine
    :param dev: a device
    :return: (coro_result, dev.status)
    """
    t = asyncio.ensure_future(showprogress(dev))
    res = await coro
    status = await t
    return res, status


async def test():
    conf = get_config().devices
    print(time.ctime(), 'open wago')
    wg = await wago_valvesystem.create('valvesystem', conf.valvesystem)
    print(wg)
    print(time.ctime(), 'start ysi relay')
    await wg.start_ysi()
    power_on = time.time()

    y = None
    try:
        y = await ysi600r.create('ysi600r', conf.ysi600r)
        print(time.ctime(), 'open YSI600R again')
        await y.open(power_on_time=power_on)
        if single_measures:
            print(single_measures, ' single measurements')
            for i in range(single_measures):
                await asyncio.sleep(1.0)
                print('{} - {}: {T:0.1f}°C, {conductivity}µS/cm, pH {pH:0.2f}'.format(i+1, time.ctime(y.readtime), **y.data))

            print('=' * 60)
        else:
            print('measurement of 10 seconds')
            print('=' * 60)
            data, status = await pwait(y.measure(5), y)
            try:
                fmt = ('{}: T={ysiT:0.1f}°C, cond={ysiConductivity:0.1f}µS/cm, pH={ysipH:0.3f}' +
                      'from {ysicount} measurements in {ysiduration:0.2f}s')
                print(fmt.format(time.ctime(), **data))
            except Exception as e:
                print(repr(e))
                print(data)
    except KeyboardInterrupt:
        pass
    finally:
        if y:
            await y.close()
        print('Reset WAGO')
        await wg.reset()
        await wg.readstatus()
        print(wg)

async def multi_test(n=1):

    for i in range(n):
        print('#' * 60)
        print(time.ctime(), 'Test #',i+1)
        await test()
        print(time.ctime(), 'sleep for 10s')
        await asyncio.sleep(10.0)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(multi_test(10))

