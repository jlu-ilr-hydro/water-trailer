import asyncio
import traceback

from .jsonclient import JsonClient
from . import DeviceError
from .. import system

debug = False

class LoggerClient(JsonClient):

    def __init__(self, name, conf):
        super().__init__(conf.host, conf.port, name=name)
        self.send_back = conf.send_back

    async def readstatus(self, no_send=False):
        if not no_send:
            await self.setdata()
        return await super().readstatus()

    async def setdata(self):
        t = system.trailer
        conf = t.conf.devices.logger
        devicedata = t.devices.devicedata()
        data = {}
        if conf.get('send_back'):
            for n, v in conf.send_back.items():
                try:
                    data[n] = eval(v, {}, devicedata)
                except Exception:
                    print('LoggerClient: could not send ', v)
                    print(traceback.print_exc())
            if debug:
                print(data)
            await self.send('setdata', **data)


async def create(name, conf):
    client = LoggerClient(name, conf)
    client.apply_config(conf)
    if conf.get('debug'):
        global debug
        debug = True

    try:
        await asyncio.wait_for(client.readstatus(no_send=True), timeout=1)
    except asyncio.TimeoutError:
        raise DeviceError('Initial communication with logger took more than 1s', 'logger')
    except OSError:
        raise DeviceError('logger is not responding on {}:{}'.format(conf.host, conf.port), 'logger')
    else:
        await client.handle_conf_event('on_create', conf)
    return client
