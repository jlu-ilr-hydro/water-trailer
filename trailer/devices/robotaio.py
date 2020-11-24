"""
Created on 16.04.2016

@author: kraft-p
"""

import asyncio
import math
import yaml
import time
import traceback

from . import aioserial

from io import BytesIO
from . import DeviceError
from .base import Device

debug = 0
maxpositionerrors = 2
defaultbottlefile = 'preferences/bottles.robot.yaml'

class PositionError(DeviceError):
    pass

class RobotCalibration:
    levels = -2, 143, 275  # mm z-Axis (m3) for the levels
    xoffset = +65  # mm offset of the x axis (m1)
    yoffset = -155  # mm offset of the y axis (m2)
    alphaoffset = -0.020, 0.06  # Offset for m1 angle in radians for left and right side
    xscale = 50.0  # bottle width x-axis
    yscale = 43.5  # bottle length y-axis
    radius = 282.0  # mm length between rotation center and outlet of m1 arm
    waste = 142.0, 690.0, 137.0  # x,y,z position of waste port in mm


def id2pos(bottleid):
    rack = bottleid // 10000
    bottle = bottleid % 10000
    level = bottle // 1000
    row = bottle % 1000 // 100
    col = bottle % 100
    return col, row, level, rack


def pos2id(col, row, level, rack=0):
    return rack * 10000 + level * 1000 + row * 100 + col

# TODO: On poserror read ERROR eg. #3E\r\n

class Motor(Device):

    def __init__(self, address, robot, maxstep, length):
        self.name='motor{}'.format(address)
        self.address = address
        self.robot = robot
        self.maxstep = maxstep 
        self.length = length
        self.lock = asyncio.Lock()
        super().__init__()
        self.data = {'pos': 0}
        self.hold_current = 0
        self.initseq = []

    def __str__(self):
        return 'M{} on {}'.format(self.address, self.robot.serial.port)

    async def do(self, *commands):
        return await self.robot.do(self.address, *commands)

    async def is_referenced(self):
        # checks if the motor is referenced
        resp = await self.do(':is_referenced')
        resp = resp[-1].strip()
        return resp[-1]=='1'

    async def goabs(self, pos):
        # if pos<0 or pos>self.length:
        #    raise DeviceWarning('position out of bounds',self)
        await self.readstatus()
        if self.data.get('poserror'):
            raise PositionError("m{} has a position error".format(self.address), self.robot)
        
        with await self.lock:
            self.data['startpos'] = self.data['pos'] 
            self.data['endpos'] = pos
            steps = pos / self.length * self.maxstep
            await self.do('y1', 'p2', 's{:+0.0f}'.format(steps), 'A')
            self.is_ready.clear()
        
    async def gorel(self, pos):
        
        await self.readstatus()
        if self.data['poserror']:
            raise PositionError("m{} has a position error".format(self.address), self.robot)

        with await self.lock:
            self.data['startpos'] = self.data['pos'] 
            self.data['endpos'] = self.data['pos'] + pos
            steps = pos / self.length * self.maxstep
            self.is_ready.clear()
            await self.do('y1', 'p1', 's{:+0.0f}'.format(steps), 'A')
            self.is_ready.clear()

    async def reference(self):
        with await self.lock:
            cmds = self.initseq + ['>1', 'p4', 'A']
            self.is_ready.clear()
            await self.do(*cmds)
            self.is_ready.clear()
        
    async def readio(self):
        res = await self.do('ZY')
        if debug>1:
            print('Got',res,'from readio')
        return int(res[0][3:])
    async def is_position_error(self):
        status = await self.do('$')
        return int(status[0][4:]) & 4

    async def stop(self, fast=True):
        await self.do('S{:d}'.format(not fast))

    async def clearposerror(self):
        await self.do('D')

    async def readstatus(self):
        with await self.lock:
            self.readtime = time.time()
            status = await self.do('$')
            if not status or not status[0]:
                raise DeviceError('No answer from status ($)', self)
            pos = await self.do('C')

            if len(status[0])<7:
                raise DeviceError('Answer from $ is too short: {}'.format(status), self)
            binstatus = int(status[0][4:])
            pos = int(pos[0][2:]) / self.maxstep * self.length        
            self.data.update(dict(ready=bool(binstatus & 1), 
                                  poserror=bool(binstatus & 4),
                                  pos=pos,
                                  status=binstatus)
                             )
            if not self.is_ready.is_set() and binstatus & 1:
                if debug:
                    print('{} is ready'.format(self))
                self.is_ready.set()
            

        if 'startpos' in self.data:
            start = self.data['startpos']
            end = self.data['endpos']
            if end - start > 0:
                self.data['progress'] = (pos - start) / (end - start)
            else:
                self.data['progress'] = 0.0
        else:
            self.data['progress'] = 0.0

    def __str__(self):
        return 'motor{}'.format(self.address)


class Robot(Device):
    def __init__(self, port='/dev/trailerRobot'):
        self.name = 'samplerobot'
        self.flushvol = 50
        self.bottlesize = 50
        length = [math.pi, 9400 * 0.054, 3900 * 0.07]
        maxstep = [-4000, -9400, 3900]
        self.serial = aioserial.Ser2Net(port, timeout=1)
        self.motors = [Motor(i + 1, self, maxstep[i], length[i]) for i in range(3)]
        super().__init__()
        self.busy = None
        self.actbottle = None
        self.radius = RobotCalibration.radius
        self.progress = lambda: 0.0
        self.is_ready.progresscallback = self.progress
        self.lock = asyncio.Lock()
        self.position_error_count = 0
        self.only_level_2 = False

    def __str__(self):
        return 'samplerobot on {port}'.format(port=self.serial.device)

    async def open(self):
        """
        Opens a serial connection to the nanotec RS485 bus and
        """
        await self.serial.open()
        for m in self.motors:
            if debug:
                print('Test', m)
            try:
                res = await asyncio.wait_for(m.do('$'), timeout=0.5)
            except asyncio.TimeoutError:
                raise DeviceError('No answer from {}'.format(m), self)
            if not res:
                raise DeviceError('No answer from {}'.format(m), self)

        m1, m2, m3 = self.motors
        # TODO: First check the status, if no answer, raise DeviceError
        # Define path attributes of each motor
        # Hartmut: Set reference switch ports
        # Commands executed only once at start of program
        await m1.do(':CL_position_window+10',':CL_position_window_time+0',
                    ':CL_following_error_window+10',':CL_following_error_timeout+100',
                    'U+0','d+1', ':port_in_a+7', 'i+85', 'r+50', 'g+8', ':gd+1', ':gn+1')
        await m2.do(':CL_position_window+10',':CL_position_window_time+0',
                    ':CL_following_error_window+10',':CL_following_error_timeout+100',
                    'U+0','d+1', ':port_in_a+7', ':port_in_b+0', ':port_in_c+0',
                    'i+75', 'r+15', 'g+1', ':gd+1', ':gn+1')
        # Attention max. operating current for MOTOR 3 = 55% - Parameter [i]
        await m3.do(':brake_ta+0', ':brake_tb+0', ':brake_tc+0',
                    ':CL_enable+0',
                    'U+0','d+0', ':port_in_a+7', # ':port_in_b+2',':port_out_b+2',
                    'i+55', 'r+0', 'g+1', ':gd+1', ':gn+1')
        # initseq of a motor is called each time the motor is referenced
        m1.initseq = ['p+4', 'd+1', 'u+50', 'o+1000', 'B+50', 'b+50', 'N0']
        m2.initseq = ['p+4', 'd+1', 'u+50', 'o+1000', 'B+50', 'b+50', 'N0']
        m3.initseq = ['p+4', 'd+0', 'u+50', 'o+400', 'B+50', 'b+50', 'N0']

    async def do_cmd(self, command):
        """Writes a single command to the controller. The command needs to include the motor number
        """
        with await self.lock:
            self.serial.write_fast((command.strip()+'\r').encode())
            if debug > 1:
                print('#{}\r'.format(command), end='->')
            s = BytesIO()
            #await asyncio.sleep(0.1)
            while True:
                a = await self.serial.read(1)
                if not a or a in (b'\r', b'\n'):
                    break
                else:
                    s.write(a)
            if debug > 1:
                print(s.getvalue().decode())
            return s.getvalue().decode()

    async def do(self, motorid, *commands):
        if self.serial is None:
            raise DeviceError('Connection to port is not open', self)
        res = []
        for cmd in commands:
            res.append(await self.do_cmd('#{}{}'.format(motorid, cmd)))
        return res

    async def do_fromfile(self, fn):
        if self.__reader is None:
            raise DeviceError('Connection to port is not open', self)
        for line in open(fn):
            # Check if the line is a command
            if line.strip() and line.strip().startswith('#'):
                cmd = line.split("'")[0].strip()
                response = await self.do_cmd(cmd)
                response = response.strip()
                if response.endswith('?'):
                    raise DeviceError('nanotec did not understand ' + cmd, self)

    async def readstatus(self):
        if self.lock.locked():
            return
        for m in self.motors:
            await m.readstatus()
            self.data.update(dict(('{}_{}'.format(m, k), v) for k, v in m.data.items()))
            self.data['poserror'] = self.data.get('poserror',False) or m.data['poserror']
        self.data['progress'] = self.progress()
        return self

    async def reference(self):
        tstart = time.time()
        if self.busy:
            raise DeviceError("Can't reference, robot does {}".format(self.busy), self)
        self.progress = lambda: 0.0
        self.actbottle = None
        self.is_ready.clear()
        await self.readstatus()
        self.busy = 'reference'
        m1, m2, m3 = self.motors
        if debug:
            print('clearposerror')
        for m in self.motors:
            await m.clearposerror()
        await self.readstatus()

        # Move M2 out of "dangerous" area
        val = await m2.readio()
        if val & 4:
            await m2.gorel(-200)
        elif val & 2:
            await m2.gorel(-100)
        self.progress = lambda: m2.progress * 0.3
        while not m2.is_ready.is_set():
            await m2.readstatus()
            io = await m2.readio()
            if debug:
                print('{:0.1f}s: m2 contacts closed: {}'.format(time.time()-tstart, io))
            if io < 2:
                break
            await asyncio.sleep(0.1)
        await m2.stop(fast=False)
        if debug:
            print('{:0.1f}s: ref m1'.format(time.time()-tstart))
            
        # Refernce m1
        is_referenced = await m1.is_referenced()
        if debug:
            print('m1 is_referenced=',is_referenced)
        #if not is_referenced:
        #await m1.gorel(math.pi/50)
        #await m1.is_ready.wait()
        await m1.reference()
        self.progress = lambda: m1.progress * 0.3 + 0.3
        await self.readstatus()
        await m1.is_ready.wait()
        if debug:
            print('{:0.1f}s: ref m2'.format(time.time()-tstart))
        # TODO: assert is_referenced
        # Move m2 10 mm to the right to ensure there is a distance to go during reference run
        is_referenced = await m2.is_referenced()
        if debug:
            print('m2 is_referenced=',is_referenced)
        #if not is_referenced:
        await m2.gorel(10.0)
        await m2.is_ready.wait()
        await m2.reference()
        self.progress = lambda: (m3.progress + m2.progress) * 0.2 + 0.6
        if debug:
            print('{:0.1f}s: ref m3'.format(time.time()-tstart))
        if not self.only_level_2:
            # Move m3 10 mm up to ensure there is a distance to go during reference run
            is_referenced = await m3.is_referenced()
            if debug:
                print('m3 is_referenced=',is_referenced)
            # if not is_referenced:
            await m3.gorel(-5.0)
            await m3.is_ready.wait()
            await m3.clearposerror()
            await m3.reference()
            if debug:
                print('{:0.1f}s: wait ref'.format(time.time()-tstart))
        await asyncio.sleep(0.2)
        m2.is_ready.clear()
        wait_tasks = [m2.is_ready.wait()]
        if not self.only_level_2:
            m3.is_ready.clear()
            wait_tasks.append(m3.is_ready.wait())
        await asyncio.wait(wait_tasks)
        if debug:
            print('{:0.1f}s: ref ready'.format(time.time()-tstart))
        self.busy = None
        self.is_ready.set()
    
    async def gotobottle(self, bottleid):
        col, row, level, rack = id2pos(bottleid)
        if self.busy:
            raise DeviceError("Can't go to bottle, robot does {}".format(self.busy), self)
        self.busy = 'goto bottle'
        if self.actbottle and self.actbottle[-1] == level:
            z = None
        else:
            # TODO: Raise if only_level_2
            z = RobotCalibration.levels[level - 1]

        y = (col - 1) * RobotCalibration.yscale + RobotCalibration.yoffset
        x = (row - 1) * RobotCalibration.xscale + RobotCalibration.xoffset
        self.actbottle = col, row, level
        await self.go(x, y, z, self.busy)
        self.busy = None

    async def gotowaste(self):
        """
        Goes to the waste port using RobotCalibration values
        """
        if self.busy:
            raise DeviceError("Can't go to waste, robot does {}".format(self.busy), self)
        await self.readstatus()
        self.actbottle = None
        _x, _y, z = [m.data['pos'] for m in self.motors]
        wx, wy, wz = RobotCalibration.waste
        await self.go(wx, wy, wz if abs(z - wz) > 1.0 else None, busy='gowaste')
        self.busy = None

    async def go(self, x, y, z=None, busy=None):
        """
        Moves the outlet to a position in the cartesian coordiante system x,y,z
        x - depth in fridge
        y - left/right in fridge
        z - height in fridge
        """

        while self.position_error_count < maxpositionerrors:
            self.is_ready.clear()
            if debug:
                print('goto({},{},{})'.format(x, y, z))
            self.busy = busy or 'go'
            m1, m2, m3 = self.motors
            r = self.radius
            y0 = 0.5 * m2.length
            alpha = math.asin(x / r)
            if y > y0:
                y2 = y - r * math.cos(alpha)
                alpha += RobotCalibration.alphaoffset[0]
            else:
                y2 = y + r * math.cos(alpha)
                alpha = math.pi - alpha + RobotCalibration.alphaoffset[1]
            self.progress = lambda: m2.progress * 0.2
            try:
                if debug:
                    print('m2->{:.1f}'.format(y0))
                await m2.goabs(y0)
                await m2.is_ready.wait()
                if z is not None:
                    # place m2 and m1 in safe position
                    self.progress = lambda: 0.2 + m1.progress * 0.2
                    if debug:
                        print('m1->{:.1f}'.format(0.0))
                    await m1.goabs(0.0)
                    await m1.is_ready.wait()
                    # go z
                    self.progress = lambda: 0.4 + m3.progress * 0.2
                    if debug:
                        print('m3->{:.1f}'.format(z))
                    await m3.goabs(z)
                    await m3.is_ready.wait()
                self.progress = lambda: 0.6 + m1.progress * 0.2
                if debug:
                    print('m1->{:.1f} pi'.format(alpha/math.pi))
                await m1.goabs(alpha)
                await m1.is_ready.wait()
                self.progress = lambda: 0.8 + m2.progress * 0.2
                if debug:
                    print('m2->{:.1f}'.format(y2))
                await m2.goabs(y2)
                await m2.is_ready.wait()
                if debug:
                    print('go is ready')
                if not busy:
                    self.busy = None
                self.is_ready.set()
            except PositionError as e:
                # On a position error, reference the robot a repeat problem
                self.position_error_count += 1
                # TODO: Log error properly
                print('!!!!!! GOT POSITION ERROR, rereference now',e)
                await self.reference()
                continue
            else:
                if self.position_error_count:
                    self.position_error_count -= 1
                return
        raise DeviceError('More than 10 position errors during less than 10 successful positions', self)



class FridgeRack(object):
        
    def __init__(self, bottlefile=None):
        self.bottlefile = bottlefile or defaultbottlefile
        try:
            self.filledbottles = yaml.load(open(self.bottlefile))
        except OSError:
            self.filledbottles = {}
        self.filledbottles = self.filledbottles or {}
        # TODO: Handle rack change 
        self.rack = 1
        self.capacity = (19 * 5 - 2) * 3

    def clear(self):
        self.filledbottles = {}

    def nextbottle(self, last=None):
        """
        Returns the next bottle id
        """
        if not last and not self.filledbottles:
            # Rack is empty
            return self.rack * 10000 + 1101
        last = last or max(self.filledbottles)
        col, row, level, rack = id2pos(last)
        # Get next
        if col < 19 - max(0, row - 4):
            col += 1
        elif row < 5:
            col = 3 # 1 + max(0, row - 3)
            row += 1
        elif level < 3:
            col = 1
            row = 1
            level += 1
        else:
            raise DeviceError('Fridge rack is full', self)
        return pos2id(col, row, level, rack)

    def countempty(self):
        return self.capacity - len(self.filledbottles)
            
    def setfilled(self, bottle_id, sample_id):
        """
        Marks the bottle (bottle_id) as filled with sample_id
        """
        self.filledbottles[bottle_id] = sample_id
        yaml.dump(self.filledbottles, open(self.bottlefile, 'w'), default_flow_style=False)
    
    def getfilled(self):
        """
        Returns a list cube in the form: levels, rows, columns
        containing the stored sample ids or 0 for empty bottles
        """
        # make general for bottle sizes / numbers
        return [[[self.filledbottles.get(pos2id(col, row, level, self.rack), 0)
                  for col in range(1, 20)]
                 for row in range(1, 6)]
                for level in [1, 2, 3]]


async def create(name, conf):
    r = Robot(conf.port)
    r.apply_config(conf)
    r.name = name
    if 'debug' in conf:
        global debug
        debug = conf.debug
    try:
        await r.open()
    except DeviceError:
        raise
    except Exception:
        raise DeviceError(traceback.format_exc(), r)
    t = asyncio.ensure_future(r.reference())
    await asyncio.sleep(0.1)
    while not r.is_ready.is_set():
        await r.readstatus()
        await asyncio.sleep(1)
    await t
    await r.handle_conf_event('on_create', conf)
    return r
