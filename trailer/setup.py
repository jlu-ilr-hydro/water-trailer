"""
Here you find the list of device modules that should be used by the sampler. 
To integrate another device add its module to the device list
@author: kraft-p
"""
import traceback
import asyncio
import sys
import time
import importlib

from .devices import DeviceError
from . import get_config

async def setup(devices):
    """
    Creates the devices from the sample.config.yaml
    :param devices:
    :return:
    """
    conf = get_config()
    t0 = time.time()

    # Create the tasks
    tasks = []
    for name, dev in conf.devices.items():
        module = importlib.import_module(dev.module)
        tasks.append(asyncio.ensure_future(module.create(name, dev)))

    for f in asyncio.as_completed(tasks, timeout=60.0):
        try:
            r = await f

        except DeviceError as e:
            dt = time.time() - t0
            print('{:5.1f}s: ERROR: {}'.format(dt, e), file=sys.stderr)

        except Exception:
            dt = time.time() - t0
            print('{:5.1f}s: ERROR!'.format(dt), file=sys.stderr)
            traceback.print_exc()

        else:
            dt = time.time() - t0
            print('{:5.1f}s: ok: {} is {}'.format(dt, r.__module__, r))
            devices[r.name] = r
    
    if devices.is_debug():
        for d in devices.values():
            print(d)
            
    await devices.handle_conf_event('on_setup_complete', conf)


