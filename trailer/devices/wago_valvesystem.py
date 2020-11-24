"""
Wrapper to the WAGO PLC based valve system

error
"""
from orderedattrdict import AttrDict
import asyncio
import traceback
from umodbus.client import tcp as mdb
import struct
from time import time

from .base import Device, DeviceError, DeviceWarning, DeviceMessage
from .. import TrailerError

debug = False

class WagoTimeout(DeviceWarning):
    def __init__(self, wago):
        msg = 'WAGO: {command} had timeout after {elapsed:0.1f}s. Actual fill: {weight:0.1f}ml'.format(**wago.data)
        super().__init__(msg, wago)

class WaterWarning(DeviceError):
    def __init__(self, wago):
        msg = 'WAGO: Detected water leak'
        super().__init__(msg, wago)

class _PLCtype:
    """
    Defines a value type in the PLC that is read as words
    via modbus
    """
    def __init__(self, size, unpack_fmt, dtype, factor=None):
        self.size = size
        self.unpack_fmt = unpack_fmt
        self.factor = factor
        self.type = dtype

    def __call__(self, words):
        """
        Converts a list of words to the type.
        len(words)==self.size!
        :param words:
        :return:
        """
        assert len(words) == self.size, 'Got {} values for {} size'
        pack = struct.pack('{}H'.format(self.size), *words)
        v = struct.unpack(self.unpack_fmt, pack)[0]
        if self.factor:
            return v / self.factor
        else:
            return v

    def pack(self, value):
        if self.factor:
            value = self.type(value * self.factor)
        b = struct.pack(self.unpack_fmt, value)
        return struct.unpack('{}H'.format(self.size), b)


class _T:
    INT = _PLCtype(1, 'h', dtype=int)
    WORD = _PLCtype(1, 'H', dtype=int)
    REAL = _PLCtype(2, 'f', dtype=float)
    TIME = _PLCtype(2, 'I', factor=1000, dtype=int)
    PROG = _PLCtype(1, 'h', factor=10000, dtype=int)
    TEMP = _PLCtype(1, 'h', factor=10, dtype=int)


class _Bitpack:
    """
    Translates a WORD to an ordered dict of True /False states
    using the names.
    """

    def __init__(self, *names):
        self.names = names

    @property
    def size(self):
        return 1 + len(self.names) // 16

    def __call__(self, words):
        """
        translates the bitpack to a list of (name, value) tuples
        :param words: a 16 bit unsigned integer
        :return: a list of (name, value) tuples
        """
        return [(name, bool(words[0] & 2**i))
                for i, name in enumerate(self.names)
                ]

    def __len__(self):
        return len(self.names)

    def __getattr__(self, item):
        if item in self.names:
            return 2**self.names.index(item)
        else:
            raise AttributeError('{} is not an attribute of {}'.format(item, self))

    def find(self, name):
        """
        Finds the value for a name
        """
        if name in self.names:
            return 2**self.names.index(name)
        else:
            return 0


def first(data, prefix=''):
    """
    Returns the first name with a "True" value in a list of (name,value) tuples
    """
    for name, value in data:
        if value and name.startswith(prefix):
            return name[len(prefix):]
    return None


class _RegisterQuery:

    def __init__(self, offset, data):
        """
        A query to the modbus registers
        :param offset: The address offset
        :param data: A list of (name, [_PLCtype | _Bitpack]) tuples
        """
        self.offset = offset
        self.data = data

    def size(self):
        return sum(t[1].size for t in self.data)

    def read(self, slave_id=0):
        """
        Returns the Modbus ADU of the query
        """
        try:
            res = mdb.read_holding_registers(slave_id, self.offset, self.size())
        except struct.error:
            raise TrailerError('Could not create Modbus-ADU for slave_id={}, offset={:x}, size={}'
                               .format(slave_id, self.offset, self.size()))
        return res

    def __call__(self, words):
        """
        Translates the words of a register query to an ordered dict
        :param words: a list of words, the response from modbus
        :return: a list of (name, value) tuples
        """
        assert len(words) >= self.size(), 'Modbus words to small for query'
        res = []

        i = 0
        # cycles through the response words
        for n,t in self.data:
            if i >= len(words):
                break
            # words for type from words list
            w = words[i:i + t.size]
            if isinstance(t, _Bitpack):
                res.extend(t(w))
            else:
                res.append((n, t(w)))
            i += t.size
        return res


COMMAND_ADDRESS = 0x3000


class WagoValvesystem(Device):
    """
    Wraps the valvesystem controller on the WAGO PLC 750-881
    using the Software fill.pro
    """
    _cmd = _Bitpack('reset', 'flush', 'fill', 'empty',
                    'fridge', 'bempty', 'ysi600r', 'calibrate', 'raise_timeout')
    _st = _Bitpack('is_running', 'is_timeout', 'is_waterwarning', 'is_ready')
    _status_query = _RegisterQuery(COMMAND_ADDRESS, [
                                            ('commands', _cmd),
                                            ('valve', _T.INT),
                                            ('tgtweight', _T.REAL),
                                            ('timeout', _T.TIME),
                                            ('status', _st),
                                            ('progress', _T.PROG),
                                            ('weight', _T.REAL),
                                            ('elapsed', _T.TIME),
                                            ('rainfill1', _T.REAL),
                                            ('rainfill2', _T.REAL),
                                            ('max_valve', _T.INT),
                                            ('smooth_factor', _T.INT),
                                            ('calib_offset', _T.REAL),
                                            ('calib_gain', _T.REAL),
                                            ('temp_trailer', _T.TEMP),
                                            ('temp_rack', _T.TEMP),
                                            ])
    slave_id = 0
    name = 'valvesystem'

    def __init__(self, host='wago', port=502):
        """

        :param host: IP-address or server name of modbus slave
        :param port: modbus port
        """
        self.host = host
        self.port = port
        super().__init__()
        self.is_ready.progresscallback = self.progress
        self.lock = asyncio.Lock()
        self.auto_calibrate = False

    def __str__(self):
        if self.data:
            return 'WAGO doing {command}/{status},weight={weight:0.1f}ml,valve={valve},timeout={timeout:0.1f}s'.format(**self.data)
        else:
            return 'WAGO, data not available'

    def progress(self):
        return self.data.get('progress', 0.0)

    async def send(self, request_adu):
        """
        Sends a modbus adu to the slave and returns the response
        data
        :param request_adu: the adu of the request
        :return: data of the response.
                 - For single read commands it is the single value
                 - for multiple read commands a list of values
                 - for single read commands the value
        """
        response = b''
        asyncio.gather()
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(request_adu)
            await writer.drain()

            for i in range(10):
                await asyncio.sleep(0.005)
                response = await reader.read(2048)
                if response:
                    break
        finally:
            writer.close()
        if not response:
            raise ConnectionAbortedError('WAGO PLC did not respond after 5 attempts')
        return mdb.parse_response_adu(response, request_adu)

    async def readstatus(self):
        """
        Reads the status from the valvesystem
        :return:
        """
        # Create request for status
        tstart = time()
        req_adu = self._status_query.read(slave_id=self.slave_id)
        # Send status request to PLC and get response
        with await self.lock:

            status = await self.send(req_adu)
            # Save response list as self.data
            self.readtime = time()
            old_waterwarning = self.data.get('is_waterwarning')
            try:
                data = self._status_query(status)
                self.data = AttrDict(data)
                self.data['command'] = first(data[:len(self._cmd)])
                self.data['status'] = first(data, 'is_')
                self.data['readtime'] = time() - tstart
            except TypeError:
                print('Status response:', status)
                raise

            # Some checks
            # Old run ready
            if self.data.is_ready and not self.is_ready.is_set():
                self.is_ready.set()
                if debug:
                    print(self.command, ' is ready!')
            # New run started
            if self.data.is_running and self.is_ready.is_set():
                self.is_ready.clear()
            # the trailer drowns but this is not raised before
            if self.data.is_waterwarning and not old_waterwarning:
                raise WaterWarning(self)

        return self

    async def _continuousread(self):
        """
        Reads every 0.1 seconds the status from the modbus as long as
        the valvesystem is running. This is used for test runs out of the normal
        cycle
        :return:
        """
        await self.readstatus()
        while self.is_running():
            await asyncio.sleep(0.1)
            await self.readstatus()

    async def _do_command(self,
                          cmd_code: int,
                          valve: int=None,
                          tgtweight: float=None,
                          timeout: float=None,
                          wait=False):
        """
        Performs a command
        :param cmd_code: The binary value of the command
        :param valve: The valve number
        :param tgtweight: the target weight in g
        :param timeout: the maximum time
        :param wait: False: Returns directly after command is submitted
                     True: Waits for is_running is false, but does not perform readstatus calls
                     'm': Monitors the valvesystem (readstatus) until is_running is false
        :return: True
        """
        await self.readstatus()
        with await self.lock:
            valve = valve or self.valve
            tgtweight = tgtweight if tgtweight is not None else self.tgtweight
            timeout = timeout or self.timeout
            values = (0, valve) + _T.REAL.pack(tgtweight) + _T.TIME.pack(timeout)
            req_adu = mdb.write_multiple_registers(slave_id=self.slave_id,
                                                   starting_address=COMMAND_ADDRESS,
                                                   values=values)
            await self.send(req_adu)
            await asyncio.sleep(0.05)
            req_adu = mdb.write_single_register(self.slave_id, COMMAND_ADDRESS, cmd_code)
            await self.send(req_adu)
            await asyncio.sleep(0.05)
            self.is_ready.clear()
        await self.readstatus()
        if wait == 'm':
            await self._continuousread()
        elif wait:
            await self.is_ready.wait()
        return True
    
    def _check_running(self):
        """
        Run this function directly after starting a command and reading the new status
        it checks if the valve system is running for sure. If not it raises a DeviceWarning
        informing about the state
        
        :returns: None
        
        """
        if not self.is_running and not self.is_ready.is_set():
            self.is_ready.set()
            raise DeviceWarning('WAGO should {command} but did not start.'.format(**self.data), self)

    async def extend_timeout(self, seconds=10):
        """
        Extends the current timeout by seconds
        :param seconds: number of seconds to extend the timeout
        :return:
        """
        await self.readstatus()
        with await self.lock:
            new_timeout = self.timeout + seconds
            req_adu = mdb.write_multiple_registers(self.slave_id, starting_address=COMMAND_ADDRESS + 4,
                                                   values=_T.TIME.pack(new_timeout))
            await self.send(req_adu)

    async def clear_command(self):
        """
        Clears the command flag
        """
        with await self.lock:
            req_adu = mdb.write_single_register(self.slave_id, COMMAND_ADDRESS, 0)
            self.is_ready.clear()
            response = await self.send(req_adu)
        return response

    async def reset(self):
        """
        Submits a reset signal to the PLC and clears all inputs
        :return:
        """
        with await self.lock:
            req_adu = mdb.write_single_register(self.slave_id, COMMAND_ADDRESS, 1)
            await self.send(req_adu)
            await asyncio.sleep(0.01)
            self.is_ready.clear()

    async def set_maxvalves(self, max_valves):
        """
        Sets the number of installed valves
        :param max_valves:
        :return:
        """
        with await self.lock:
            req_adu = mdb.write_single_register(slave_id=self.slave_id, address=0x3000 + 16, value=max_valves)
            await self.send(req_adu)
        return True

    async def set_smooth_factor(self, smoothfactor: int):
        """
        Sets the length of the low pass filter for the scale in cycles
        :param smoothfactor:

        """
        
        with await self.lock:
            req_adu = mdb.write_single_register(slave_id=self.slave_id, address=0x3000 + 17, value=smoothfactor)
            await self.send(req_adu)

    async def set_calibration(self, offset=None, gain=None):
        """
        Sets the calibration parameters
        :param offset: The calibration offset in ml
        :param gain: the calibration gain in ml/DU
        :return:
        """
        offset = offset or self.data.calib_offset
        gain = gain or self.data.calib_gain
        values = _T.REAL.pack(offset) + _T.REAL.pack(gain)
        req_adu = mdb.write_multiple_registers(slave_id=self.slave_id, 
                                               starting_address=0x3000 + 18, 
                                               values=values)
        with await self.lock:
            return await self.send(req_adu)

    async def start_ysi(self):
        """
        Opens the YSI relay to turn the YSI on
        :return:
        """
        cmd = self._cmd.ysi600r
        await self._do_command(cmd)

    async def flush(self, valve: int, timeout: float, with_ysi600=False, wait=False):
        """
        Flushes the tubes until timeout
        :param valve: The valve to use for flushing
        :param timeout: The time in seconds
        :param with_ysi600: True, if the YSI600R should be turned on
        :param wait: False: Returns directly after command is submitted
                     True: Waits for is_running is false, but does not perform readstatus calls
                     'm': Monitors the valvesystem (readstatus) until is_running is false
        :return:
        """
        cmd = self._cmd.flush
        if with_ysi600:
            cmd += self._cmd.ysi600r
        await self._do_command(cmd, valve, timeout=timeout, wait=wait)

    async def fill(self, valve: int, target_vol: float, timeout: float=120.0, wait=False):
        """
        Fills the reservoir through the filter
        :param valve: the valve number 1..16
        :param target_vol: the target volume in the reservoir in ml
        :param timeout: timeout time in s. If targetweight is not reached, is_timeout is latched
        :param wait: False: Returns directly after command is submitted
                     True: Waits for is_running is false, but does not perform readstatus calls
                     'm': Monitors the valvesystem (readstatus) until is_running is false
        :return:
        """
        cmd = self._cmd.fill + self._cmd.raise_timeout

        await self._do_command(cmd, valve, tgtweight=target_vol, timeout=timeout, wait=wait)
        self._check_running()
        if wait and self.data.is_timeout:
            raise WagoTimeout(self)

    async def empty(self, target_vol: float=0.0, to_fridge=False, timeout: float=120.0,
                    wait=False, ignore_timeout=False):
        """
        Empties the reservoir in Fridge / Waste direction

        :param target_vol: the target volume in the reservoir in ml
        :param to_fridge: True when the sample goes to the fridge
        :param timeout: timeout in s. If targetweight is not reached, is_timeout is latched
        :param wait: False: Returns directly after command is submitted
                     True: Waits for is_running is false, but does not perform readstatus calls
                     'm': Monitors the valvesystem (readstatus) until is_running is false
        :param ignore_timeout: if True, do not raise an exception on timeout
        :return:
        """
        cmd = self._cmd.empty
        if to_fridge:
            cmd += self._cmd.fridge
        if not ignore_timeout:
            cmd += self._cmd.raise_timeout
        await self._do_command(cmd, tgtweight=target_vol, timeout=timeout, wait=wait)
        self._check_running()
        if wait and self.is_timeout and not ignore_timeout:
            raise WagoTimeout(self)

    async def empty_complete(self, timeout=None, to_fridge=False):
        """
        Calls self.empty(target_vol=0.0, timeout=timeout, wait=True)
        If a timeout occurs, the scale offset is recalibrated
        :param timeout: timeout in s. If targetweight is not reached, the offset is calibrated.
                        Be generous, or you calibrate to a wrong value
        :param to_fridge: If True, the water is routed to the sample fridge. Good for flushing,
                          bad for filling samples
        :return: If calibrated return a TrailerLoggable, else return Noe
        """
        await self.readstatus()
        timeout = timeout or max(20, self.data.weight/2)
        # Try to empty only down to 2 ml to have a greater chance to avoid a timeout
        await self.empty(target_vol=2, timeout=timeout, wait=True,
                         to_fridge=to_fridge, ignore_timeout=True)

        if debug:
            print('empty_complete: {} timeout occured, empty for 5s to be sure'
                  .format(['no', ''][self.is_timeout]))

        # Make sure the device is really empty
        await self.empty(target_vol=-10, timeout=5.0, wait=True, ignore_timeout=True)

        # Calibrate the offset if auto_calibrate is on
        if self.auto_calibrate:
            old_co, new_co = await self.calibrate_offset()
            if debug:
                print('empty_complete: done. Old/new offset: {:0.2f}/{:0.2f}ml'
                      .format(old_co, new_co))
            # return the difference
            return DeviceMessage('Auto calibration: old/new offset: {:0.2f}/{:0.2f}ml'
                                 .format(old_co, new_co), self)
        # Make sure the device is really empty
        return None

    async def bempty(self, valve: int, target_vol: float,
                     timeout: float=None, wait=False,
                     ignore_timeout=False):
        """
        Empties the reservoir through the filter into a valve
        :param valve: the valve number 1..16
        :param target_vol: the target volume in the reservoir in ml
        :param timeout: timeout time in s. If targetweight is not reached, is_timeout is latched
        :param wait: False: Returns directly after command is submitted
                     True: Waits for is_running is false, but does not perform readstatus calls
                     'm': Monitors the valvesystem (readstatus) until is_running is false
        :param ignore_timeout: If True, this command raises no is_timeout
        :return:
        """
        cmd = self._cmd.bempty
        if not ignore_timeout:
            cmd += self._cmd.raise_timeout
        await self._do_command(cmd, valve, tgtweight=target_vol, timeout=timeout, wait=wait)
        self._check_running()

        if wait and self.is_timeout:
            raise WagoTimeout(self)

    async def calibrate_offset(self):
        """
        Performs a simple calibration of the offset using the actual weight
        Call only when you are sure the reservoir is empty
        :return: An (old, new) calibration offset tuple
        """
        await self.readstatus()
        # co means calibration offset, cg calib_gain
        co = self.data.calib_offset
        cmd = self._cmd.calibrate
        await self._do_command(cmd, tgtweight=0.0)
        return co, self.calib_offset

    async def empty_source(self, valveid, filling_value, target_value=0, timeout=300):
        """
        Starts a flush from valveid with a 5s timeout.
        If filling_value>target_value, the flushing continuous for another 5s
        :param valveid: Valve to empty, eg. 1
        :param filling_value: value that shows the filling level, eg. 'rainfill1'
        :param target_value: Value that should be reached, eg. 0.0%
        :param timeout: The maximum time to use for this thing
        :return:
        """
        await self.flush(valveid, 5)
        while self.data[filling_value] > target_value and self.timeout < timeout:
            await self.extend_timeout(5)
            await asyncio.sleep(5)
        await self.is_ready.wait()

    def itervalveids(self):
        for i in range(self.data.get('max_valve',12)):
            yield i+1

async def create(name, conf) -> WagoValvesystem:

    vs = WagoValvesystem()
    vs.name = name
    vs.apply_config(conf)
    if conf.get('debug'):
        global debug
        debug = True
    try:
        await asyncio.wait_for(vs.readstatus(), timeout=1)
    except DeviceError:
        raise
    except asyncio.TimeoutError:
        raise DeviceError('Initial communication with WAGO took more than 1s', name)
    except Exception:
        raise DeviceError(traceback.format_exc(), name)
    await vs.handle_conf_event('on_create', conf)
    return vs
