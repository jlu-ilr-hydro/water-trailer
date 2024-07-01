'''
Created on 19.06.2015

@author: kraft-p
'''
import asyncio
import time
import traceback
import datetime

from attrdictionary import AttrDict

from .schedule import Schedule
from .devices import Devices, DeviceError
from .exceptions import TrailerLog, TrailerException, TrailerError, TrailerInfo
from . import db, get_config



class ScheduleLoop(object):
    """
    The loop through a schedule
    """
    def __init__(self, system):
        
        self.system = system
        self.schedule = Schedule()
        self.sample = None
        
        self.active = False
        self.__idle = asyncio.Future()

        self.__measure = None

    def check_events(self):
        """
        Checks the event sources of the schedule
        """
        for e in self.schedule.events:
            source = e(self.system.devices)
            # Get event tag if event is fired
            if source:
                try:
                    for s in source:
                        self.schedule.inject_once(s)
                except TypeError:
                    self.schedule.inject_once(int(source))
    
    async def stop(self):
        """
        Stops the loop
        """
        self.active = False
        for n, T in [('measure', self.__measure), ('idle', self.__idle)]:
            if T:
                if not T.done():
                    T.cancel()
                try:
                    await T
                except asyncio.CancelledError:
                    db.log(TrailerLog('cancelled ' + n, owner='system'))

    async def do(self, conf):
        """
        Checks if a measurement is due and starts it in the self.__measure task
        It is designed to be called continuously by the main system loop
        :param conf: configuration.measurement
        :return: String representing the current task
        """
        if not self.active:
            await self.stop()
            return 'not active'

        # No measurement active, but a source is due
        elif (self.__measure is None and not self.__idle.done() and
              self.schedule.is_due()):
            # Get a new sample from the schedule

            source_id, sample_time = self.schedule.nextsample()
            with db.session_scope() as session:
                sample = db.Sample.create(session, source_id, sample_time)
                if sample:
                    session.commit()
                    self.sample = sample.to_json(withsource=True)
                else:
                    self.sample = None
            if self.sample:
                from . import measure
                # importlib.reload(measure)
                # Do measure
                self.__measure = asyncio.ensure_future(
                        asyncio.wait_for(measure.measure(self.sample),
                                         timeout=conf.timeout))
                self.__idle.set_result(True)
                await self.__idle
            return 'start'

        # A measurement is active
        elif self.__measure:
            # measurement is ready
            if self.__measure.done():
                # Finalize measurement
                try:
                    await self.__measure
                except TrailerException as e:
                    db.log(e)
                    # If this is an error, not just a Warning, stop the schedule
                    if e.level <= 2:
                        db.log(TrailerInfo('Schedule stops'))
                        self.active = False
                        return 'error: ' + str(e)
                    else:
                        self.schedule.starttime -= datetime.timedelta(seconds=self.schedule.time_per_source)
                except asyncio.CancelledError:
                    self.active = False
                    db.log(TrailerLog('Measurement of {} was cancelled'.format(self.sample.name)))
                    return 'stop'

                except asyncio.TimeoutError:
                    self.active = False
                    db.log(TrailerError('Measurement of {} took more than {:0.0f}s, stopped measurement'
                           .format(self.sample.name, conf.timeout), owner='system'))
                    return 'stop'

                except Exception as e:
                    self.active = False
                    traceback.print_exc()
                    db.log(TrailerException(repr(e), owner='system', level=1))
                    return 'error: ' + str(e)

                finally:
                    self.__measure = None
                self.sample = None
                if not self.__idle.done():
                    self.__idle.set_result(True)
                await self.__idle
                self.__idle = asyncio.Future()
                return 'finished'
                   
            else:
                # measurement not ready
                return 'measuring'

        # Stopping the schedule
        elif self.__idle.done():
            try:
                await self.__idle
            except asyncio.CancelledError:
                pass
            self.active = False
            db.log(TrailerLog('stopping schedule'))
            return 'stop'

        else:
            # Nothing to do
            if self.schedule.peek():
                # if there is something scheduled
                return 'wait'
            else:
                # if nothing is scheduled and only manual
                # and event measurements will come
                return 'idle'



           
class Trailer(object):
    """
    The central object of the trailer.
    Is the "owner" of all devices and the schedule
    """

    def __init__(self, conf=None):
        self.active = True
        self.action = ''
        self.schedule_action = ''
        self.data = AttrDict()
        # A dictionary of callbacks providing progress (0..1) for different
        # keywords
        self.progresscallbacks = AttrDict()
        self.async_loop = asyncio.get_event_loop()

        # A list of (name,progress value) tuples to indicate progress of different tasks
        self.progress = []
        self.devices = Devices()
                    
        self.loop = ScheduleLoop(self)
        self.looptask = None
        self.checktask = None
        self.start = time.time()
        self.conf = conf or get_config()

    def calc_progress(self):
        res = []
        for name, cb in self.progresscallbacks.items():
            if callable(cb):
                res.append((name, min(cb(), 1.0)))
            else:
                try:
                    res.append((name, float(cb)))
                except (TypeError, ValueError):
                    res.append((name, None))
        return res

    def idleprogress(self):
        return (time.time() - self.start) % 10.0 / 10.0

    def shutdown_threadsafe(self):
        self.active = False
        # try:
        #     self.async_loop.call_soon_threadsafe(self.shutdown())
        # except Exception as e:
        #     raise


    def get_data(self):
        devdata = self.devices.devicedata()
        devdata['WATER'] = self.data
        return devdata

    async def main(self):
        """
        Updates the status of the devices by readstatus
        - until: A callable without parameters that evaluate to
                True (ready) or False (busy)
        - timeout: The timeout in seconds
        - devices: The devices that should be checked by calling readstatus
        """
        self.conf = get_config()
        conf_time = time.time()
        db.log(TrailerInfo('Trailer starts up', owner='system'))
        while self.active:
            dctime = time.time()
            # read the config every second
            if dctime - conf_time > 1.0:
                self.conf = get_config()
                conf_time = time.time()
            # read the status from all devices
            await read_devices(self.devices.values(), self.conf)
            # Check schedule events
            dcduration = time.time() - dctime
            self.data.devicereadtime = dcduration
            self.progress = self.calc_progress()

            if self.loop.active:
                # Check for event sources
                self.loop.check_events()
                # Check for next source
                self.data.schedule = await self.loop.do(self.conf.measure)
            else:
                self.data.schedule = 'not active'
            waittime = self.conf.device_read_rate - dcduration
            await asyncio.sleep(max(0.1, waittime))
        db.log(TrailerInfo('Server is going to shutdown'))
        await self.loop.stop()
        await self.devices.handle_conf_event('on_shutdown', get_config())


    def to_json(self):
        current = AttrDict()
        current.progress = self.progress
        current.sample = self.loop.sample
        current.action = self.action
        current.time = datetime.datetime.now().strftime('%H:%M:%S')
        return AttrDict(
            devices=self.get_data(),
            current=current
        )

async def read_devices(devices, conf):
    """
    Reads the devices to update their status
    :param devices: a list of devices
    :param conf: the config (get_config)
    :return: None
    """
    # Create the reading tasks for the devices that needs to be read
    pending = [(d, asyncio.ensure_future(d.readstatus()))
               for d in devices
               if d and d.time_to_read()]

    start_read = time.time()

    # Containers for devices returned fine and devices raising exceptions
    ok = []
    exceptions = []

    # Now we are waiting for read_status Tasks to return and handle the results as they are available
    # asyncio.as_completed is a bit funny (wrapped Tasks, unclear timeout handling
    # - tried it and discarded due to problems)
    # Instead we are looping as long as there are pending tasks (not done) and the
    # device timeout is not hit
    timeout = conf.device_timeout.seconds
    while pending and (time.time() - start_read < timeout):
        # Wait a bit
        await asyncio.sleep(0.05)
        # Get exceptions from the done tasks
        not_ready = []
        for d, T in pending:
            if T.done():
                e = T.exception()
                if e:
                    exceptions.append((d, e))
                else:
                    ok.append((d, T.result()))
            else:
                not_ready.append((d, T))
        pending = not_ready

    # Handle timeouts
    for d, T in pending:
        T.cancel()
        try:
            await T
        except asyncio.CancelledError:
            pass
        # Handle Timeout
        # Raise the counter for timeouts on that device
        d.timeout_counter += 1
        if d.timeout_counter >= conf.device_timeout.times:
            exceptions.append((d, TrailerException('{}.read_status() had a timeout {} times. Deactivated.'
                                                   .format(d.name, conf.device_timeout.times),
                                                   level=3, owner='system')))
            d.active = False

    # Reset timeout counter of ok devices
    for d, r in ok:
        d.timeout_counter = 0

    # Handle exceptions
    for d, e in exceptions:
        if isinstance(e, TrailerException):
            db.log(e)
        else:
            traceback.print_exc()
            db.log(TrailerException('{}.read_status() returned an unknown error: {}'.format(d, e), 1, owner='system'))




trailer = Trailer()

