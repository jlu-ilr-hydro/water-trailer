#!/usr/bin/python3

'''
Created on 30.03.2016

@author: kraft-p
'''
import sys
import serial
import time
import asyncio

from trailer import get_config
from trailer.devices import robotaio

def serial_readuntil(s, c_end):
    buffer = bytearray()
    while True:
        c = s.read(1)
        if not c or c == c_end.encode():
            break
        buffer.append(ord(c))
    return buffer.decode()

stop = asyncio.Event()
async def showprogress(dev):
    loop = asyncio.get_event_loop()
    tstart = loop.time()
    while not stop.is_set():
        await dev.readstatus()
        p = dev.progress()
        print('{:5.1f}s {}{:5.1%} {}'.format(loop.time()-tstart,
                                            [dev.motor1_status,dev.motor2_status,dev.motor3_status],
                                            p, '*' * int(p*50)), end='\r')
        await asyncio.sleep(0.1)
    print()

async def test(conf, refonly=False, waste=False):
    # Creates and references the robot
    robotaio.debug = 2
    r = await robotaio.create('samplerobot', conf)

    if refonly:
        exit()
    t = asyncio.ensure_future(showprogress(r))
    await asyncio.sleep(3.0)
    # 1 Rack [1, immer], 2 Level [1..3], 3 Row [1..5], 4-5 column [01..19]
    bottles = [11101, 11401,
        11102,  11302, 
        11104,  11304, 11504,
        11106,  11306, 11506,
        11108,  11308, 11508,
        11110,  11310, 11510,
        11112,  11312, 11512,
        11114,  11314, 11514,
        11116,  11316, 11516,
        11118,  11318, 11518,
        11119,  11419,
        ]
    for nb in bottles:
        if waste:
            print('waste')
            await r.gotowaste()
        print('goto bottle #',nb)
        await r.gotobottle(nb)
        print('wait')

        # wait time between bottles
        await asyncio.sleep(1.0)

    stop.set()
    await t
    

def console():
    """
    Starts an interactive console for nanotec commands
    """
    conf = get_config().devices.samplerobot
    def isint(s):
        try:
            i = int(s)
            return True
        except:
            return False
    s = serial.Serial(conf.port, baudrate=115200, timeout=0.3)
    s.read(100)
    while True:
        print('Enter command in the form #[Motor][Command][+/-Value], eg. "#3p1" and press enter')
        print('q to quit')
        cmd=input('Command:').strip()
        if cmd.lower().startswith('q'):
            break
        if cmd.strip()=='$':
            for motor in range(1,4):
                s.write('#{}$\r'.format(motor).encode())
                response = serial_readuntil(s, '\r')
                print(' -> ',response.strip())
        elif cmd.startswith('#') and isint(cmd[1]):
            s.write((cmd + '\r').encode())
            response = serial_readuntil(s, '\r')
            print(' -> ',response.strip())
        else:
            print('Command did not start with #[Motor]')


def runfile(conf, fn):
    """
    Runs a file with nanotec commands. Lines not starting with # are ignored
    :param fn: File name to run
    :return:
    """
    s = serial.Serial(conf.port, baudrate=115200, timeout=0.3)
    s.read(100)
    print('Command', (40-len('Command')) * ' ', 'Answer')
    for cmd in open(fn):
        cmd = cmd.strip()
        # Check if line is a nanotec command
        if cmd.startswith('#'):
            s.write(cmd.encode()+b'\r')
            response = serial_readuntil(s, '\r')
            if response:
                response = response.split("'")[0].strip()
            print('#' + response)
        else:
            print(cmd)
    s.close()

if __name__ == '__main__':
    conf = get_config().devices.samplerobot
    if 's' in sys.argv:
        s = serial.Serial(conf.port, baudrate=115200, timeout=0.3)
        
        for m in [1,2,3]:
            s.write('#{}S+1\r'.format(m).encode())
            print(s.read(5).decode().strip())
        
        s.close()
    elif 'm' in sys.argv:
        s = serial.Serial(conf.port, baudrate=115200, timeout=0.3)
        s.read(100)
        s.write(b'#3p1\r')
        print(s.read(100).decode().strip())
        s.write(b'#3s-50\r')
        print(s.read(100).decode().strip())
        s.write(b'#3A\r')
        print(s.read(100).decode().strip())
    elif 'c' in sys.argv:
        console()
    elif 'l' in sys.argv or 'r' in sys.argv:
        loop = asyncio.get_event_loop()
        robotaio.debug = 0
        loop.run_until_complete(test(conf, 'r' in sys.argv, 'w' in sys.argv))
    elif 'f' in sys.argv:
        runfile(sys.argv[2])

    else:
        print('Usage: test/robot.py [smcflr]')
        print()
        print('Direct communication (robotaio.py not involved)')
        print('  s: Stops all motors')
        print('  m: Moves m3 5cm up')
        print('  c: Opens a console to write commands directly')
        print('  f: Runs a file of nanotec commands and displays the result. Filename should follow')
        print('Complete tests using robotaio.py')
        print('  r: Reference the motors')
        print('  l: Run bottle list in line 41ff of this file')

        


