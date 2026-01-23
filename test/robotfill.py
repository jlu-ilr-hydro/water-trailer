#!/usr/bin/python3

import asyncio
from trailer.devices import robotaio as robot
from trailer.devices import wago_valvesystem
from time import ctime
import trailer

stop = asyncio.Event()
async def showprogress(dev):
    loop = asyncio.get_event_loop()
    tstart = loop.time()
    dev.is_ready.clear()
    while not dev.is_ready.is_set():
        await dev.readstatus()
        if dev.data.get('poserror'):
            print('!!!!!!!!!!!!!! POESERROR')
            raise RuntimeError('Position ERROR!')
        p = dev.progress()
        print('{:5.1f}s {:5.1%}{}'.format(loop.time()-tstart, p, '*' * int(p*50)), end='\r')
        await asyncio.sleep(0.1)
    print()
    return await dev.readstatus()

async def pwait(coro, dev):
    t = asyncio.ensure_future(showprogress(dev))
    await coro
    status = await t
    return status


class RobotTest:
    # Volume to fill in a bottle
    fillvol = 25

    def __init__(self, r: robot.Robot, vs: wago_valvesystem.WagoValvesystem,
                 refillvalve: int, repeattime: float = 60):
        self.r = r
        self.vs = vs
        self.fridge = robot.FridgeRack('preferences/test.bottles.robot.yaml')
        # self.fridge.clear()
        self.refillvalve = refillvalve
        self.repeattime = repeattime

    async def refill(self):
        await self.vs.readstatus()
        status = self.data
        if status['weight'] < self.fillvol * 5:
            status = await pwait(self.vs.fill(self.refillvalve, target_vol=500, timeout=120), self.vs)
            if status['is_timeout']:
                raise RuntimeError('Not enough water at valve {}'.format(self.refillvalve))
            else:
                print(ctime(), '    reservoir filled to {weight:0.2f}ml'.format(**status))
        else:
            print(ctime(), '    no refill needed reservoir at {weight:0.2f}ml'.format(**status))

    async def fillbottle(self):
        await self.vs.readstatus()
        status = self.data
        if status['weight'] < self.fillvol:
            raise RuntimeError('Not enough water available, {:0.2f}ml/{:0.2f}ml'.format(status['weight'], self.fillvol))

        status = await pwait(self.vs.empty(status['weight'] - self.fillvol, timeout=60, to_fridge=True), self.vs)

        if status['is_timeout']:
            raise RuntimeError('Empty to fridge got timeout')

    async def waste(self):
        await pwait(self.r.gotowaste(), self.r)
        await self.fillbottle()

    async def nextbottle(self, sample: int):
        print(ctime(), '    refill reservoir if necessary')
        await self.refill()
        nb = self.fridge.nextbottle()
        print(ctime(), '    goto bottle', nb)
        await pwait(self.r.gotobottle(nb), self.r)
        await self.vs.readstatus()
        status = self.data
        print(ctime(), '    fill bottle {}, {:6.3f}l'.format(nb, status['weight']))
        await self.fillbottle()
        print(ctime(), '    mark bottle {} as filled with sample {}'.format(nb, sample))
        self.fridge.setfilled(nb, sample)
        print(ctime(), '    goto waste')
        await self.waste()

    async def run(self, nbottles=100000):
        nbottles = min(nbottles, self.fridge.countempty())
        for sample in range(nbottles):
            print()
            print('#' * 60)
            waittask = asyncio.sleep(self.repeattime)
            print(ctime(), 'SAMPLE:', sample)
            await self.nextbottle(sample)
            await waittask

async def createdev(refillvalve, repeattime):
    robot.debug = 0
    create_task = asyncio.gather(robot.create(trailer.address.robot),
                                 wago_valvesystem.create(trailer.address.wago))
    r, vs = await create_task
    return RobotTest(r, vs, refillvalve, repeattime)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    test = loop.run_until_complete(createdev(9, 1))
    loop.run_until_complete(test.run(3))
