'''
Created on 17.03.2016

@author: kraft-p
'''

import asyncio
import datetime
import time
from attrdictionary import AttrDict

from .base import Device, DeviceError


class FakeDevice(Device):
    """
    A proxy device for off line tests
    """

    def __init__(self, name, config):
        
        self.name = name
        self.starttime = time.time()
        self.frequency = config.get('frequency', 20.0)
        super().__init__()
        self.data = config
        self.lock = asyncio.Lock()

    async def readstatus(self):
        async with self.lock:
            await asyncio.sleep(0.1)
            self.data['time'] = datetime.datetime.utcnow()
            self.data['progress'] = self.progress()
            self.data['event'] = 0
            self.data.chapter = AttrDict()
            self.data.chapter.bla = 1
            self.data.chapter.test = 2
            #self.data.chapter['bli'] = AttrDict()
            #self.data.chapter.bli['nochmal'] = 1
            self.data.chapter.blub = "1"
            self.data.detailsetup = AttrDict()
            self.data.detailsetup.bla = 42

            self.readtime = time.time()
            if self.starttime:
                if time.time() > self.starttime + self.frequency:
                    self.starttime = None
                    # print time.ctime(), '{} is ready'.format(self.name)
                    self.is_ready.set()
                else:
                    self.is_ready.clear()
            else:
                self.is_ready.clear()

            self.data['ready'] = self.is_ready.is_set()
        return self
        
    def floatvalues(self):
        res = {}
        for k in self.data:
            try:
                res[k] = float(self.data[k])
            except:
                continue
        return res

    def progress(self):
        elapsed = time.time() - (self.starttime or time.time())
        return elapsed / self.frequency

    async def reset(self):
        self.starttime = time.time()
        self.is_ready.clear()
        await asyncio.sleep(0.1)
        return

    async def doaction(self, duration=10.0):
        async with self.lock:
            self.is_ready.clear()
            await asyncio.sleep(0.3)
            self.frequency = duration or 10.0
            self.starttime = time.time()

    async def measure(self):
        duration = self.data.get('integrationtime') or 10.0
        await self.doaction(duration)
        await self.is_ready.wait()
        return

    def __repr__(self):
        return 'FakeDevice({})'.format(self.name)


class ValveSystemFake(FakeDevice):

    def __init__(self, name, config):
        super().__init__(name, config)
        self.action = None
        self.defaulttimeout = 60.
        self.emptytime = 10.
        self.data.weight = 0.0
        self.data.tgtweight = 0.0
        flags = ('reset', 'flush', 'fill', 'empty','fridge', 'bempty', 'ysi600r', 'calibrate',
                 'is_running', 'is_timeout', 'is_waterwarning')
        for flag in flags:
            self.data[flag] = False

        fvalues = ('tgtweight', 'timeout', 'weight',
                   'elapsed', 'rainfill1', 'rainfill2', 'progress',
                   'calib_offset', 'calib_gain')
        for fv in fvalues:
            self.data[fv] = 0.0
        ivalues = 'valve', 'timeout', 'max_valve', 'smooth_factor'
        for iv in ivalues:
            self.data[iv] = 0

    async def flush(self, source_id, timeout=10.0, wait=False, **kwargs):
        self.data.valve = source_id
        await self.doaction(5.0)
        self.action = 'flush'
        if wait:
            await self.wait(30)
    async def fill(self, source_id, samplevol=0, timeout=10.0, wait=False, **kwargs):
        self.data.valve = source_id
        await self.doaction(5.0)
        self.action = 'fill'
        if wait:
            await self.wait(30)
    async def empty(self, targetvol=0, timeout=10.0, wait=False, **kwargs):
        await self.doaction(5.0)
        self.action = 'empty'
        if wait:
            await self.wait(30)
    async def empty_complete(self, timeout=2.0, wait=True, **kwargs):
        await self.doaction(2.0)
        self.action = 'empty'
        if wait:
            await self.wait(timeout+5)

    async def start_ysi(self, **kwargs):
        await asyncio.sleep(0.08)
        return

    async def wait(self, timeout=None):
        """
        Shortcut to self.is_ready.wait() with timeout
        """
        try:
            await asyncio.wait_for(self.is_ready.wait(),
                                   timeout or 30.0)
        except asyncio.TimeoutError:
            raise DeviceError('{} waited more than {}s'.format(self, timeout), self)


class FakeRobot(FakeDevice):
    
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.flushvol = 0.1
        self.bottlesize = 0.05
    
    async def open(self):
        await asyncio.sleep(0.3)
    
    def __str__(self):
        return 'samplerobot faked'
    
    def progress(self):
        return super().progress()

    async def reference(self):
        await self.doaction(10.0)
        await self.is_ready.wait()
        return True
        
    async def gotowaste(self):
        print('gotowaste')
        await self.doaction(10.0)
        await self.is_ready.wait()
        return True
    async def gotobottle(self, bottleid):
        await self.doaction(10.0)
        await self.is_ready.wait()
        return True


async def create(name, conf):
    if name == 'valvesystem':
        dev = ValveSystemFake(name, conf)
    else:
        dev = FakeDevice(name, conf)
    await asyncio.sleep(0.2)
    return dev
