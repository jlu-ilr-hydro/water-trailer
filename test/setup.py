#!/usr/bin/env python3
import asyncio
import time
import yaml

from trailer import get_config
from trailer.devices import Devices
from trailer.setup import setup


if __name__ == '__main__':
    conf = get_config()
    print('Will do setup for:\n', '\n    - '.join(conf.devices))

    loop = asyncio.get_event_loop()
    devices = Devices()
    #devices.set_debug()
    loop.run_until_complete(setup(devices))
    time.sleep(0.5)
    data = loop.run_until_complete(devices.readstatus())
    for n, d in devices.items():
        print('\n')
        print(n, d)
        print('-' * 60)
        for k, v in d.data.items():
            print('    ',k,':', v)
