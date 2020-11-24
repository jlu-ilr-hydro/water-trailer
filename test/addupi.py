#!/usr/bin/python3
import sys
sys.path.append('.')

import os
import asyncio
import yaml
from trailer.logger.bus.addupi import Sensor, Bus

def finddevice(tag):
    """
    Checks if a node in the addUPI response is a device
    :param tag: BeautifulSoup tag
    :return: bool
    """
    return tag.has_attr('class') and tag['class'] == 'DEVICE'

async def listdevices(bus):
    """
    Lists all devices on the bus
    """
    print('Get Devices')
    soup, url = await bus.read(function='getconfig')
    devices = soup.find_all(finddevice)
    print('Found ', len(devices), ' devices')
    for dev in devices:
        print('    id={id} name={name}'.format(**dev.attrs))


async def test(listdev=False, *sensor_ids):
    try:
        #url = 'http://demo.adcon.at:8080/addUPI'
        url = 'http://10.42.0.100/addUPI'
        print('Create bus on ', url)
        bus = Bus(url, 'root', 'adcon')
        print('Login')
        session = await bus.login(10)
        print('Got session-id:', session)
    except AddUPIError as e:
        print(e)
        return
    try:
        if listdev:
            await listdevices(bus)
        if sensor_ids:
            print('Create sensors')
            for sid in sensor_ids:
                sensor = await bus.configsensor(sid)
                print('New sensor', sensor)
                print('Read sensor')
                data = await bus.readsensor(sensor)
                print('Data from ', sensor)
                for v in data:
                    print(v)
                    
            yaml.dump(bus.__asdict__(), sys.stdout, default_flow_style=False)

    finally:
        print('Logout')
        await bus.logout()
        print('Session-id:', bus.session)

async def readfromsavedbus(fn='preferences/addupi-2017-03.bus.yaml'):
    busdict = yaml.load(open(fn))
    bus = Bus.from_dict(busdict)
    print(bus)
    print('=' * 50, '\n')

    await bus.login()
    try:
        for sensor in bus.sensors:
            data = await bus.readsensor(sensor)
            print('Data from ', sensor)
            print('-' * 50)
            for v in data:
                print('   ', v)
    finally:
        await bus.logout()



if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    if len(sys.argv)==1:
        print('Usage:\ntest/addupi.py [ls] [id1,id2,id3...]')
        exit()
    #loop.set_debug(1)
    if os.path.exists(sys.argv[1]):
        loop.run_until_complete(readfromsavedbus(sys.argv[1]))
    else:
        listdev = 'ls' in sys.argv
        if listdev:
            sys.argv.remove('ls')
        sensor_ids = [int(s) for s in sys.argv[1:]]
        loop.run_until_complete(test(listdev, *sensor_ids))
    print('\nexit')
