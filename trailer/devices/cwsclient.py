"""
Created on 11.06.2015

@author: kraft-p


"""


from .jsonclient import JsonClient
from .base import ProgressEvent
from . import DeviceError
import asyncio
import time
from orderedattrdict import AttrDict

debug = False

class _CWSMeasurement(asyncio.Future):
    """
    A class holding a measurement sample
    """

    def __init__(self, name, cws, sample):
        super().__init__()
        self.name = name
        self.cws = cws
        self.start = time.time()
        self.can_empty = ProgressEvent(name='CWS:' + name,
                                       progresscallback=lambda: self.progress)
        self.data = AttrDict()
        self.data.time_to_cell = 0.0
        self.data.time_to_switch = 0.0
        self.data.time_to_ready = 0.0
        self.sample = sample

    def pcb_name(self):
        return 'CoWS[{}]'.format(self.name)

    def progress(self):
        return (time.time()-self.start)/self.cws.readytime

    def update(self, data):
        self.data.update(data)
        if self.data.time_to_switch <= 0 and not self.can_empty.is_set():
            self.can_empty.set()
        if self.data.time_to_ready <= 0.0 and not self.done():
            self.set_result(data)

    def __lt__(self, other):
        return self.start < other.start

    def __getattr__(self, attr):
        if attr in self.data:
            return self.data[attr]
        else:
            raise AttributeError('CWS-Measurement does has no attribute and no data enty "' + attr + '"')

    def __str__(self):
        res = self.name
        if self.done():
            res += ': ready' #, at {:0.1f}ppm H2O'.format(self.result()['mean_H2O'])
        elif self.time_to_cell > 0:
            res += ': {:0.1f}s until cell'.format(self.time_to_cell)
        elif self.time_to_switch > 0:
            res += ': {:0.1f}s until can empty'.format(self.time_to_switch)
        elif self.time_to_ready > 0:
            res += ': {:0.1f}s until ready'.format(self.time_to_ready)

        return res

    async def stop(self):
        self.cws.killsample(self.name)
        self.cws.measurements.remove(self)
        super().cancel()




class CWSclient(JsonClient):

    def __init__(self, picarrohost='127.0.0.1', tcpport=51211):
        super().__init__(picarrohost, tcpport, name='cwspicarro')
        self.measurements = []
        self.data = AttrDict()
        self.valuetypes = ['mean_d18O', 'mean_d2H',
                           'mean_H2O', 'std_d18O', 'std_d2H', 'std_H2O']

    def progress(self):
        if 'cellsample' in self.data and self.cellsample:
            return self.cellsample['progress']
        elif 'linesample' in self.data and self.linesample:
            return self.linesample['progress']
        else:
            return 0.0

    async def __startsample(self, name, port):
        response = await self.send('sample', name=name, port=port)
        if 'error' in response:
            raise DeviceError(response['error'], self)
        else:
            return response

    async def readstatus(self, data=None):
        self.readtime = time.time()
        await super().readstatus()
        samplelist = [self.data.get('readysample'),
                      self.data.get('cellsample'),
                      self.data.get('linesample')]
        samples = AttrDict((s['name'], s) for s in samplelist if s)

        for m in self.measurements:
            if m.name in samples and not m.done():
                m.update(samples[m.name])
        return self

    @property
    def measurement(self) -> _CWSMeasurement:
        try:
            return self.measurements[0]
        except:
            return None

    async def measure(self, samplename: str, port: int=3, sampledata=None, done_callback=None) ->_CWSMeasurement:
        """
        Starts a cws measurement and returns the future _CWSMeasurement. Will return fast.
        :param samplename: The string representation of the current sample. Is shown in the Picarro coordinator
        :param port: Port of the continuous water sample (1..4)
        :param sampledata: complete sample description
        :param done_callback: a callback that is executed when the measurement is done
        :return: The future _CWSMeasuremment
        """
        if self.measurements and (len(self.measurements) >= 2 or not self.measurements[0].can_empty.is_set()):
            raise DeviceError('Current measurement is not ready', self)
        else:
            await self.__startsample(samplename, port)
            new_measurement = _CWSMeasurement(samplename, self, sampledata)
            self.measurements.append(new_measurement)
            await self.readstatus()
            if done_callback:
                new_measurement.add_done_callback(done_callback)
            return new_measurement

    async def killsample(self, name=None):
        response = await self.send('killsample', name=name)
        return response

    async def setparams(self, integrationtime=None, switchtime=None, readytime=None):
        """
        Changes the parameters of the cwsclient
        :param integrationtime: Time to average the result, standard 120s
        :param switchtime: Time after which a source switch may happen, usually 180s less then readytime
        :param readytime: Time to perform a complete measurement
        :return:
        """
        resp = await self.send('setparameters',
                               integrationtime=integrationtime,
                               switchtime=switchtime,
                               readytime=readytime
                               )
        return resp
            
    async def stopcws(self):
        resp = await self.send('stop')
        return resp

async def create(name, conf) -> CWSclient:

    client = CWSclient()
    client.name = name
    client.apply_config(conf)
    try:
        await asyncio.wait_for(client.readstatus(), timeout=5)
    except DeviceError:
        raise
    except asyncio.TimeoutError:
        raise DeviceError('Initial communication with cwspicarro took more than 5s', 'cwspicarro')
    except Exception as e:
        raise DeviceError(repr(e), client)
    else:
        await client.handle_conf_event('on_create', conf)
    return client
