import asyncio
import time

class TimeRaster:
    def __init__(self, seconds, offset=0):
        self.seconds = seconds
        self.offset = offset % seconds

    def due_in(self):
        now = time.time()
        return self.seconds - (now - self.offset) % self.seconds

    def progress(self):
        return 1 - self.due_in() / self.seconds

    def __str__(self):
        return 'every {}, {}, {} ... seconds'.format(*[s*self.seconds+self.offset for s in range(3)])

every10s = TimeRaster(10)
every30s = TimeRaster(30)
every1minute = TimeRaster(60)
every5minutes = TimeRaster(5 * 60)
every15minutes = TimeRaster(10 * 60)
every30minutes = TimeRaster(30 * 60)
every1hour = TimeRaster(60 * 60)


class ReadTask(asyncio.Future):
    async def read(self):
        try:
            res = await self.bus.read_all()
        except Exception as e:
            self.set_exception(e)
        else:
            self.set_result(res)

    def result_or_exception(self):
        if self.exception():
            return self.exception()
        else:
            return self.result()

    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.task = asyncio.ensure_future(self.read())

    def __repr__(self):
        return 'T({})'.format(self.bus)


class Schedule:
    """
    Schedules the read out of the logger busses it relates to timerasters
    """

    def __init__(self, seconds, busses=None, offset=0, onread=None, *, loop=None):
        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop
        self.busses = busses or []
        self.raster = TimeRaster(seconds, offset)
        print('Schedule: 1st reading in {:0.1f}s'.format(self.raster.due_in()))
        self.onread = onread
        self.task = self.loop.call_later(self.raster.due_in(), asyncio.ensure_future, self.read())

    def __str__(self):
        return ','.join(str(bus) for bus in self.busses) + ' (' + str(self.raster) + ')'

    def cancel(self):
        self.task.cancel()
        print(time.ctime(), 'Cancelled:', self)

    async def read(self):
        # loop.call_later is not precise. make sure the time to run has really come
        if self.raster.due_in() < self.raster.seconds * 0.5:
            await asyncio.sleep(self.raster.due_in())
        # Read the busses
        pending = [ReadTask(bus) for bus in self.busses]
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=self.raster.due_in())
            if self.onread:
                self.onread([(d.bus, d.result_or_exception()) for d in done])

        self.task = self.loop.call_later(self.raster.due_in(), asyncio.ensure_future, self.read())




if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    schedules = [Schedule(5,'abc'), Schedule(5, 'xyz', offset=3)]
    loop.call_later(300, schedules[0].cancel)
    loop.run_forever()
