#!/usr/bin/python3
import sys
sys.path.append('.')
import asyncio
from datetime import datetime
from trailer.logger.bus import maja, Bus
from trailer import address, get_config
import serial


def interactive():

    s = serial.Serial(address.maja, baudrate=115200, timeout=0.3)

    while True:
        print('Usage:\n?... : MAJA command\nquit : Exit program')
        for cmd in 'gps utc inputs vpwr vign brdtmp smda vrst'.split():
            print('   ?{}'.format(cmd))
        cmd = input('command:').strip()
        if cmd == 'quit':
            break
        else:
            s.write((cmd + '\r\n').encode())
            l1 = s.readline().decode().strip()
            if not l1:
                print('ERROR: No answer from MAJA')
            elif l1 == 'error':
                print('ERROR: {} not understood'.format(cmd))
            elif l1 == 'ok':
                print('OK')
            else:
                print('ANSWER:', l1)
                l2 = s.readline().decode().strip()
                if l2 != 'ok':
                    print('ERROR: 2nd line is not "ok"')



async def sensortest():

    majabus = Bus.from_file('preferences/maja.bus.yaml')
    print(majabus)
    #majabus.to_file('preferences/maja.bus.yaml')
    while True:
        values = await majabus.read_all()
        print(datetime.now().isoformat())
        for v in values:
            print('    {v.name}:{v.value} [{v.unit}]'.format(v=v))
        print('-' * 40)

        await asyncio.sleep(1.0)




if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    if 'i' in sys.argv:
        interactive()
    elif 's' in sys.argv:
        loop.run_until_complete(sensortest())
    else:
        print('Usage:\ntest/maja.py [i s]')
        print('    i   - interactive mode, minimal code testing')
        print('    s - track the sensors. To save the file use a UNIX pipe')
