
import os
import asyncio
import time
import traceback
from attrdictionary import AttrDict
from datetime import datetime
from ..devices.jsonclient import JsonServer
from .bus.base import Bus, Value
from .csvlogger import Csv

loggerport = 51213


class ScheduledServer(JsonServer):
    """
    A JsonServer with no own read capabilities. It's update function
     should be used as a callback for a logger.schedule.Schedule

     The server responds only to the ? and ?? commands
    """

    def __init__(self, port=loggerport, serve_all=False):

        super().__init__(port=port, serve_all=serve_all)
        self.data = AttrDict()


    def update(self, results):
        """
        Callback for a bus read schedule
        :param results: a list of (bus, list(bus.Value)) tuples
        :return: Number of results created
        """
        if self.verbose:
            print(time.ctime() + ': update busses:' + ','.join(str(b) for b,r in results))
        i = 0
        for bus, values in results:
            if isinstance(values, Exception):
                self.data[str(bus)] = str(Exception)
            else:
                if str(bus) in self.data:
                    del self.data[str(bus)]
                for v in values:
                    node = self.data
                    # goto deepest folder
                    vnames = v.name.split('.')
                    for vname in vnames[:-1]:
                        node = node.setdefault(vname, AttrDict())
                    node[vnames[-1]] = v.value
                    i += 1
        return i



class ServeLog(ScheduledServer):

    def __init__(self, port=loggerport, outfile='csvlogger.csv', serve_all=False):
        super().__init__(port, serve_all=serve_all)
        self.extra_data = AttrDict()
        self.extra_data_time = None
        self.schedule = None
        self.outfile = outfile

    def update(self, results):
        if self.extra_data:
            res = []
            for name, value in self.extra_data.items():
                res.append(Value(value, name=name, time=self.extra_data_time))
            results.append(('external_data', res))
            self.extra_data = None

        if self.outfile == 'db':
            from .db import submit
            res = []
            for bus, r in results:
                if isinstance(r, Exception):
                    print(time.ctime(), bus, end=': ')
                    print(r)
                else:
                    res.extend(r)
            try:
                newvalues = submit(res)
            except Exception:
                traceback.print_exc()
            else:
                t = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
                print(t,
                      ', '.join(str(b) for b, _ in results),
                      '\n'.join('    new value: ' + nv for nv in newvalues)
                      )

        else:
            with Csv(self.outfile) as csv:
                for bus, r in results:
                    print(time.ctime(), bus, end=': ')
                    if isinstance(r, Exception):
                        print(r)
                    else:
                        csv(r)
                        print('ok')
        res_len = super().update(results)
        self.data.result = AttrDict()
        self.data.result.time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
        self.data.result.size = res_len

    def getdata(self):
        if self.schedule:
            self.data['schedule'] = AttrDict()
            self.data['schedule']['seconds'] = self.schedule.raster.seconds
            self.data['schedule']['offset'] = self.schedule.raster.offset
            self.data['schedule']['progress'] = self.schedule.raster.progress()
        return self.data

    async def close(self):
        if self.schedule:
            self.schedule.cancel()
            await asyncio.sleep(1.0)
        return await super().close()


    @property
    def busses(self):
        if self.schedule:
            return self.schedule.busses
        else:
            return []

    def do_list(self):
        """
        Lists the loaded busses as string representation
        """
        return [str(b) for b in self.busses]

    def do_listbusfiles(self):
        """
        Returns a list of available bus description files and their text representation
        e.g.: [['preferences/test1.bus.yaml','TestSocketBus on 127.0.0.1 (5 sensors)'],
               ['preferences/test2.bus.yaml','TestSerialBus on /dev/ttyS0 (1 sensors)']]
        """
        res = []
        for f in os.listdir('preferences'):
            if f.endswith('.bus.yaml'):
                bus = Bus.from_file(f)
                res.append([f, str(bus)])
        return res

    def do_changetime(self, seconds=None, offset=None):
        """
        Changes the timeing of the schedule
        :param seconds: time gap between measurements
        :param offset: offset to the full multiple of the time gap
        """
        if self.schedule:
            if seconds:
                self.schedule.raster.seconds = seconds
            if offset is not None:
                self.schedule.raster.offset = offset

    def do_setdata(self, **kwargs):
        """
        Sets additional values to log
        """
        if self.verbose:
            print('Recieved data: ')
            for k, v in kwargs.items():
                print(k, ': ', v)
        self.extra_data_time = datetime.utcnow()
        self.extra_data = kwargs


