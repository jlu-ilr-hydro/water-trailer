'''
Created on 05.04.2016

@author: kraft-p

Creates a connection over RS232 to the YSI600R multiprobe

the Software assumes the following setting:
Realtime measurement on start up

'''
import asyncio

from trailer import address
from .base import Device, TimedEvent, ProgressEvent
from . import DeviceWarning, DeviceError
import time
import traceback
import math
from attrdictionary import AttrDict
from serial import Serial
debug = False


class YSIIntegrator:

    def progress(self):
        return self.count / self.n
    
    def __init__(self, measurements):

        self.is_ready = ProgressEvent(self.progress, 'ysi integrator')
        self.count = 0
        self.n = measurements
        self.T = 0
        self.cH = 0
        self.cond = 0
        self.start = time.time()
        
    def append(self, data):
        
        if self.is_ready.is_set():
            raise RuntimeError('Integrator is finished')
        self.count += 1
        self.T += data.T
        self.cH += 10**(-data.pH)
        self.cond += data.conductivity
        if self.count >= self.n:
            self.is_ready.set()
    
    def __call__(self):
        """
        Does the averaging over the data so far
        :return: An OrderedDict with:
                 ysiT, ysiConductivity, ysipH, ysicount
        """
        res = AttrDict()
        res.ysiT = self.T / self.count
        res.ysiConductivity = self.cond / self.count
        res.ysipH = -math.log10(self.cH / self.count)
        res.ysicount = self.count
        res.ysiduration = time.time() - self.start

        return res


class YSI600R(Device):
    """
    A wrapper for the YSI 600R Multiprobe in continuous mode

    Basic idea of the code is to read continuously from the device to
    prevent serial buffer clogging with old data. Co-Method open should be called soon
    after power on of the probe (see measure.py)
    """
    name='ysi600r'
    def __init__(self):
        self.__open = False
        self.lock = asyncio.Lock()
        self.port = '/dev/trailerYSI'
        self.integrationtime = 10.0
        super().__init__()
        self.is_ready = TimedEvent(self.integrationtime, 'YSI600R measure')
        self.timestep = 1.0
        self.timeout = 10
        self.readtask = None
        self.integrator = None

    def __str__(self):

        return 'YSI600R ({}) is {}'.format(self.port, ['off', 'on'][int(self.__open)])

    def progress(self):
        return self.is_ready.progress()

    async def open(self, power_on_time=None):
        """
        opens the connection to the sensor and feeds any buffered string
        :param power_on_time: timestamp when YSI was powered. If None assume now
        :return:
        """
        if self.__open:
            return
        power_on_time = power_on_time or time.time()
        # Wait for boot up
        waittime = 6.0 - (time.time() - power_on_time)
        if debug:
            print('YSI: wait {:0.2f}s for booting'.format(waittime))
        await asyncio.sleep(waittime)

        # Set open flag
        self.__open = True
        # Start the readtask, it will continuously read from the serial port
        loop = asyncio.get_event_loop()
        self.readtask = loop.run_in_executor(None, self.__read, loop)

        # Is ready progress is only used for measurement tasks, default is no progress
        # progresscallback is changed in the measurement co-method
        self.is_ready.progresscallback = lambda: 0.0
        self.is_ready.clear()

        # Attempt to get data, should work after a few seconds
        for i in range(100):
            await asyncio.sleep(0.1)
            if 'T' in self.data:
                break
        else:
            try:
                await self.close()
            except DeviceError:
                raise
            else:
                raise DeviceError('no response while open', self)

        

    async def close(self):
        """
        Stops the continous reading
        :return:
        """
        self.__open = False
        if not self.readtask:
            return
        if debug:
            print(time.ctime(), 'Closing YSI: waiting for readtask to finish')
        while not self.readtask.done():
            await asyncio.sleep(0.1)
            if debug:
                print(time.ctime(), 'Closing YSI: still waiting for readtask')
        await self.readtask

        if debug:
            print(time.ctime(), 'Closing YSI: await readtask done')

        await asyncio.sleep(0.1)

    def __read(self, loop):
        """
        Continous read function. Reads data from the device
        as long as it is open. Stops with close. To be run in an Executor
        as loop.run_in_executor(self.read)
        :return:
        """
        readstart = time.time()
        if debug:
            print(time.ctime(), '    open serial port')
        # Open a normal serial port
        with Serial(self.port, baudrate=9600, timeout=0.3) as com:
            # Feed in buffered data to clear any pending characters
            buffer = b'x'
            while buffer:
                buffer = com.read(1024)
                if buffer and debug:
                    print(time.ctime(), 'consumed {} bytes from serial:\n{}'.format(len(buffer), buffer.decode()))
            if debug:
                print(time.ctime(), '   start read loop')
            try:
                while self.__open:
                    tstart = time.time()
                    time.sleep(0.1)
                    line = com.readline()
                    if debug > 1:
                        print(line.decode().strip())
                    # Remove Garbage from the line
                    line = line.replace(b'\x00', b'').strip()
                    if line.strip():
                        data = line.split()
                        try:
                            self.data.T = float(data[2])
                            self.data.conductivity = float(data[3])
                            self.data.pH = float(data[4])
                            self.data.duration = time.time()-tstart
                            self.data.timestamp = time.time()
                        except (ValueError, TypeError, IndexError):
                            if debug:
                                print('Strange answer from YSI after {:0.2f}s: {}'.format(time.time()-readstart, line))
                            continue

                        if debug > 1:
                            print('Got value from YSI after {:0.2f}s'.format(time.time()-readstart))
                        readstart = self.readtime = time.time()

                        if self.integrator and not self.integrator.is_ready.is_set():
                            loop.call_soon_threadsafe(self.integrator.append, self.data)

                        time.sleep(max(0, self.timestep - (time.time()-tstart)))

                    elif (time.time() - readstart) > self.timeout:
                        # Over 10s without result
                        self.is_ready.set()
                        self.__open = False
                        raise DeviceError('No answer from YSI in 10s, stop reading', self)

                    else:
                        if debug > 1:
                            print('No answer from YSI for {:0.2f}s'.format(time.time() - readstart))
            except Exception:
                if debug:
                    import traceback
                    traceback.print_exc()
                raise
            finally:
                if debug:
                    print('exit read() while loop')

        if debug:
            print(time.ctime(), '   COM port closed, exit read loop')

    async def readstatus(self):
        """
        Pseudo coroutine to look like a device. NOOP
        :return:
        """
        # release shortly the loop
        self.readtime = time.time()
        await asyncio.sleep(0)
        return self

    async def measure(self, integrationtime=None):
        """
        Starts an time integrated measurement with self.integrationtime values
        and waits for the values performed
        :return: A tuple of the device itself and the result
        """
        if not self.__open:
            raise DeviceWarning('Tried to measure on a closed device', self)
        # Get integration time from parameter or from default
        integrationtime = integrationtime or self.integrationtime

        if debug:
            print('start measurement for {:0.1f}s'.format(integrationtime))
        # Create a new integrator
        self.integrator = YSIIntegrator(integrationtime)

        # Set the progress callback to the integrator
        self.is_ready = ProgressEvent(self.integrator.progress, 'YSI measurement')
        # Wait for the integrator to be full
        await self.integrator.is_ready.wait()
        # Measurement is ready, throw event
        self.is_ready.set()
        # Set the progress to 100%
        self.is_ready.progresscallback = lambda: 1.0
        # Return the averaged data of the integrator
        return self, self.integrator()

async def create(name, conf):
    """
    Creates and tests a YSI600R class
    Takes 5s
    """

    ysi = YSI600R()
    ysi.name = name
    verbose = conf.get('verbose', False)
    ysi.apply_config(conf)
    try: # Open ysi
        if verbose:
            print('open ysi relay', end='...')
        await ysi.open()
    except DeviceError:
        raise
    except Exception:
        traceback.print_exc()
        raise DeviceError(traceback.format_exc(), ysi)

    await asyncio.sleep(1.0)

    try: # close ysi
        await ysi.close()
        if verbose:
            print('ok')
    except DeviceError:
        raise
    except Exception:
        traceback.print_exc()
        raise DeviceError(traceback.format_exc(), ysi)
    else:
        await ysi.handle_conf_event('on_create', conf)
    return ysi
