"""
Created on 12.06.2015

@author: kraft-p
"""
import asyncio

import datetime
import traceback
import itertools

from orderedattrdict import AttrDict

from trailer.devices.cwsclient import _CWSMeasurement
from . import TrailerInfo, TrailerLog, get_config
from .system import trailer
from .db import log, Sample, session_scope
from .db.log import time_since_log
from .db.send import send_update
from .exceptions import TrailerError, TrailerException, TrailerWarning
from .devices import DeviceError, DeviceWarning
from .devices.base import TimedEvent

F = asyncio.ensure_future



def __loglog(msg):
    log(TrailerLog(msg))

def __check_stop_conditions(conf):
    pass

class SourceEmpty(TrailerWarning):
    def __init__(self, source, valvesystem):
        super().__init__('Tried to sample {:0.1f}ml from {}, but got only {:0.1f}ml after {:0.1f}s'
                         .format(valvesystem.tgtweight, source.name, valvesystem.weight, valvesystem.elapsed),
                         owner='measure')

def saveisotopes(m: _CWSMeasurement):
    """
    Function to be used as done_callback for an CWS measurement
    saves the relevant parameters to the db
    """

    # Check if __saveisotopes is called correctly. Since it should only be called as a add_done_callback,
    # it should be ok. Just to be sure
    if not m.done():
        raise TrailerError('measure.isotopes is called before CWS-measurement {} is ready'.format(m))
    if not m.sample or 'id' not in m.sample:
        raise TrailerError('Called done callback of CWS-Measurement {} but no sample data given'.format(m))

    # Create a list of valid valuetype names like mean_d18O or std_d2H
    valuetypes = list('_'.join(l) for l in itertools.product(['mean', 'std'], ['d18O', 'd2H', 'H2O']))

    # Get result from measurement
    result = m.result()

    # Filter result dict for valuetypes
    filtered_result = AttrDict((vt, result[vt]) for vt in valuetypes if vt in result)
    filtered_result.cows_readytime = m.cws.data.readytime
    filtered_result.cows_switchtime = m.cws.data.switchtime

    if not filtered_result:
        # Valuetypes are not in the result
        av_vt = ', '.join(result.keys())
        raise TrailerError('Got wrong keys from CWS-measurement: {} expected: {}'
                           .format(av_vt, ', '.join(valuetypes)))

    if m.pcb_name() in trailer.progresscallbacks:
        del trailer.progresscallbacks[m.pcb_name()]

    try:
        # now save the result to the db
        with session_scope() as session:
            log(TrailerLog('CWS: Save results for {}'.format(m)), session)
            osample = session.query(Sample).get(m.sample['id'])
            osample.addvalues(filtered_result)
            osample.ok = True
            m.cws.measurements.remove(m)
    except Exception as e:
        log(TrailerError('CWS: ' + repr(e)))


class __LiquidMeasurement:

    def __init__(self, sample, conf):
        super().__init__()
        self.sample = sample
        self.conf = conf
        self.samplevol = conf.samplevol
        self.pcb = AttrDict()
        self.phase = 0
        self.phasecount = 1
        self.add_pcb('measure: '+sample.source.name, lambda: self.phase/self.phasecount)
        self.samplerobot_wastetask = None
        self.cwsmeasurement = None

    def log(self, msg):
        log(TrailerLog(msg, owner='measurement'))

    def add_pcb(self, name, f):
        self.pcb[name] = None
        trailer.progresscallbacks[name] = f

    def rm_pcb(self, *names):
        for name in names:
            if name in self.pcb:
                del self.pcb[name]
                del trailer.progresscallbacks[name]

    def finish(self):
        for name in self.pcb:
            if name in trailer.progresscallbacks:
                del trailer.progresscallbacks[name]
        send_update(last_sample=self.sample.id)
        self.pcb = []
        self.log(self.sample.name + ' finished')

    async def __flush(self):
        """
        Manages phase 1 of the measurement, flushing the outside tubes
        and empty the reservoir if the CoWS is at stage "can_empty"
        :return:
        """
        valvesystem = trailer.devices.get('valvesystem')
        assert valvesystem, "Cannot flush without a valvesystem"
        cwspicarro = trailer.devices.get('cwspicarro')
        pcb = trailer.progresscallbacks
        source = self.sample.source
        flushtime = source.flushtime or 60
        if cwspicarro and cwspicarro.measurement:
            await asyncio.sleep(max(0, cwspicarro.measurement.data.time_to_switch - flushtime - 10))
        # *********************************************
        self.phase += 1
        self.add_pcb('flush', valvesystem.progress)
        self.add_pcb('empty0', 0)
        trailer.action = 'reservoir content'
        # Flush the tubes
        self.log('PHASE1: start flush')
        await valvesystem.flush(source.valveid, flushtime, wait=True)
        self.add_pcb('flush', 1)
        self.log('flush ready')

        if cwspicarro and cwspicarro.measurement:
            self.log('CWS: wait for {}'.format(cwspicarro.measurement))
            await asyncio.wait_for(cwspicarro.measurement.can_empty.wait(), timeout=cwspicarro.readytime)
            self.log('CWS: {}'.format(cwspicarro.measurement))

        self.log('complete flushing')
        await valvesystem.reset()
        # Do a complete emptying, takes 5 s
        self.add_pcb('empty0', valvesystem.progress)
        log(await valvesystem.empty_complete())
        self.rm_pcb('empty0', 'flush')
        self.log('{name} flushed and empty'.format(**self.sample))

    def finalize_isotopes(self, m):
        saveisotopes(m)
        self.finish()


    async def __fill_empty_fill(self):
        """
        This coroutine manages phases 2,3 and 4
        fill of reservoir, empty of reservoir and fill again

        :return: the sampled volume in ml
        """

        valvesystem = trailer.devices.get('valvesystem')
        sample = self.sample
        source = sample.source
        tofridge = self.samplerobot_wastetask is not None
        self.add_pcb('fill1', 0)
        self.add_pcb('empty1', 0)
        self.add_pcb('fill2', 0)
        # *********************************************
        self.phase += 1
        # Fill reservoir first time
        #
        self.add_pcb('fill1', valvesystem.progress)
        self.log('PHASE2: fill #1')
        try:
            await valvesystem.fill(source.valveid, self.samplevol,
                                   wait=True, timeout=self.samplevol * self.conf.fill_timeout + 30)
        except DeviceWarning:
            raise SourceEmpty(source, valvesystem)

        self.log('{name} filled reservoir 1st time. Act. vol={kg:0.3g}l'.format(
                  kg=valvesystem.weight, **sample))
        self.add_pcb('fill1', 1)

        # *********************************************
        self.phase += 1
        # Empty reservoir again, use water to flush the robot
        # if the sample will be stored in the fridge
        self.log('PHASE3: empty#1')
        self.add_pcb('empty1', valvesystem.progress)
        if tofridge:
            await asyncio.wait_for(self.samplerobot_wastetask, timeout=5.0)
        log(await valvesystem.empty_complete(to_fridge=tofridge))

        self.log('{name} emptied reservoir 1st time. Act. vol={v:0.3g}ml'
                 .format(v=valvesystem.weight, **sample))
        self.add_pcb('empty1', 1)

        # *********************************************
        self.phase += 1
        # Fill reservoir 2nd time
        self.log('PHASE4: fill #2')
        self.add_pcb('fill2', valvesystem.progress)
        try:
            await valvesystem.fill(source.valveid, self.samplevol,
                                   wait=True, timeout=self.samplevol * self.conf.fill_timeout + 30)
        except DeviceWarning:
            raise SourceEmpty(source, valvesystem)

        self.rm_pcb('fill1', 'empty1', 'fill2')

        self.log('{name} filled reservoir 2nd time. Act. vol={v:0.3g}ml'
                 .format(v=valvesystem.weight, **sample))

        # Save samplevol
        with session_scope() as session:
            osample = session.query(Sample).get(sample.id)
            osample.time = datetime.datetime.utcnow()
            if valvesystem.data.get('elapsed'):
                 osample.addvalues(flushspeed=valvesystem.weight / valvesystem.elapsed)
            osample.addvalues(samplevol=valvesystem.weight)


    async def __throughflow_measurement(self):
        """
        Manages the throughflow sensors (PHASE 6), by now ysi600r and ProPS
        :return:
        """
        phase = 5
        loop = asyncio.get_event_loop()
        # Get some shortcuts for devices and stuff
        valvesystem = trailer.devices.get('valvesystem')
        ysi600r = trailer.devices.get('ysi600r')
        tribox = trailer.devices.get('tribox')
        sample = self.sample
        source = sample.source
        conf = self.conf.throughflow

        # *********************************************
        self.phase += 1
        # Measure ProPS and ysi600r
        self.add_pcb('throughflow', 0.0)

        if ysi600r or tribox:
            self.log('PHASE6: Measure ProPS and/or ysi600r')
            self.log('Open ysi600r')
            # import trailer.devices.ysi600r
            # trailer.devices.ysi600r.debug = 2

            solutemeasureflush = conf.flushtime


            # Create throuflow and switch on ysi600R
            try:
                # Time in seconds the flushing should run
                # sum of flushtime needed to have new water to measure, the length of the integrationtime
                # and another 10s as buffer
                if ysi600r:
                    flush_timeout = solutemeasureflush + ysi600r.integrationtime + 10.0
                else:
                    flush_timeout = solutemeasureflush + 10.0

                # Let another min of time to complete the measurements after the flush has stopped
                measure_timeout = flush_timeout + 120.0
                self.add_pcb('throughflow', lambda: valvesystem.progress())
                # Let the water flow through the throughflow measurement system,
                # with the ysi switched on
                await valvesystem.flush(source.valveid,
                                        flush_timeout,
                                        with_ysi600=bool(ysi600r))

                if ysi600r:
                    # Open the ysi600r, this includes the booting time
                    mp_open = F(ysi600r.open())
                    await asyncio.sleep(solutemeasureflush)
                    await mp_open
                else:
                    await asyncio.sleep(solutemeasureflush)

                # Do measurements
                self.log('start throughflow measurement')

                # Make the measurement tasks
                pending = [(dev, asyncio.ensure_future(dev.measure())) for dev in [ysi600r, tribox] if dev]
                start_time = loop.time()
                try:
                    # Loop the measurement results as they are completed
                    while pending and (loop.time() - start_time < measure_timeout):
                        not_ready = []
                        for dev, T in pending:
                            asyncio.sleep(0.05)
                            if T.done():
                                with session_scope() as session:
                                    try:
                                        # try to get the result, a measure function should always return the device as a
                                        # first return. Will raise any exception produced in the coroutine
                                        _, result = await T

                                    except TrailerError as e:
                                        # log a Trailer error (usually a DeviceError)
                                        log(e, session)

                                    except Exception:
                                        # log unknown errors
                                        log(TrailerError(traceback.format_exc()), session)

                                    else:
                                        # Everything's fine. Dump result to db
                                        osample = session.query(Sample).get(sample.id)
                                        log(TrailerLog('{} data to db'.format(dev), owner='measurement'), session)
                                        osample.addvalues(result)
                                        # Remove current device from pending list, since it is handled
                            else:
                                not_ready.append((dev, T))
                        pending = not_ready

                except asyncio.TimeoutError:
                    # Took too long to measure. But bark only on the devices not handled yet
                    timeout_devices = ', '.join(str(dev) for dev, T in pending)
                    log(TrailerWarning('Measuring {} took longer than {:0.0f}'
                                       .format(timeout_devices, measure_timeout), self))

            finally:
                # In any case, close the ysi600r
                if ysi600r:
                    await ysi600r.close()
                await valvesystem.reset()
                self.add_pcb('throughflow', 1.0)

        else:
            log(TrailerLog('Just wait, no throughflow device on', owner='measure'))
            # If no throughflow measurements are available, wait for 10s
            timeout = TimedEvent(10.0)
            self.add_pcb('throughflow', timeout.progress)

            await asyncio.sleep(10.0)


    async def __sample_to_fridge(self):
        """
        Manages PHASE 7 & 8, fill sample into fridge
        :return:
        """

        valvesystem = trailer.devices.get('valvesystem')
        samplerobot = trailer.devices.get('samplerobot')
        sample = self.sample
        self.log('PHASE7: Proceed with robot')
        # *********************************************
        self.phase = 7
        # Flush robot
        self.add_pcb('flush_robot', valvesystem.progress)
        self.add_pcb('robot_to_bottle', 0)
        # Recall waste, but should be done on measure start
        await self.samplerobot_wastetask
        await valvesystem.empty(samplerobot.flushvol, to_fridge=True, wait=True)

        # *********************************************
        self.phase += 1
        # Fill sample in robot
        # Position the robot
        rack = samplerobot.get_rack()
        sample.storageid = rack.nextbottle()
        self.log('PHASE 8: robot go to {}'.format(sample.storageid))
        self.add_pcb('robot_to_bottle', samplerobot.progress)
        await samplerobot.gotobottle(sample.storageid)
        # Empty the reservoir into the sample
        await valvesystem.empty(samplerobot.bottlesize, to_fridge=True, wait=True)
        self.log('robot filled'.format(sample.storageid))
        rack.setfilled(sample.storageid, sample.id)
        self.add_pcb('robot_to_bottle', 1)


    async def run(self):
        """
        Measures a sample from an outside source using the given instruments

        Schedule is as follows:
            1. flush
            2. fill
            3. empty
            4. fill
            5. start cws
            6. postion samplerobot
            7. flush to ProPS/ysi600r
            8. wait for ProPS/ysi600r
            9. wait for cws
            10. empty reservoir and fill samplebottle
            11. empty all

        Attributes
         - sample: A sample object, needs to have the following attributes:
            - time: a datetime.datetime to get the sample time
            - source: The water source this sample is taken from
                - valveid: The valve port (11,12..21,..44)
                - flushtime: Time to flush the source in seconds
                - samplevolume: Volume to take for the sample
            - storageid: int-Position in the fridge, or 0 if the sample should
                         not be stored
            - addcomment(str): Adds a message to the sample comment
            - addvalues(**values): Adds values by its valuename
        - log(object): A callable to log messages and Exceptions.
        - valvesystem,cwspicarro,tribox,ysi600r,samplerobot: Devices to be used
                    during the measurement of a sample


        Properties of the sample robot:
            - nextbottle() : returns the bottle number of the next sample bottle
            - goto(pos): Goes to a sample bottle position
            - reset(): Robot goes to the internal waste port
        """
        sample = self.sample
        source = sample.source

        valvesystem = trailer.devices.get('valvesystem')
        samplerobot = trailer.devices.get('samplerobot')
        cwspicarro = trailer.devices.get('cwspicarro')
        self.phasecount = 6
        if samplerobot:
            self.phasecount += 2
        if cwspicarro:
            self.phasecount += 2

        try:
            self.phase = 0
            # TODO: Store only some samples, now storing them all
            tofridge = bool(samplerobot)  # and bool(sample['storageid'])

            log(TrailerInfo('{name} started'.format(**sample)))

            if tofridge:
                self.log('samplerobot: goto waste')
                self.sample_robot_waste_task = asyncio.ensure_future(samplerobot.gotowaste())
            else:
                self.sample_robot_waste_task = None

            # Calculate sample volume
            if tofridge:
                self.samplevol += samplerobot.flushvol + samplerobot.bottlesize
            if cwspicarro:
                self.samplevol += 50

            # **********************************************
            # PHASE 1: Flush the outside tubes
            await self.__flush()
            # **********************************************
            # PHASE 2,3,4 fill empty refill cycle
            await self.__fill_empty_fill()

            # *********************************************
            # PHASE 5
            # Start CWS sample
            self.phase += 1
            cwswaittask = None
            if cwspicarro:
                # Start new sample
                sample_name = '{name}(#{id})'.format(name=source['name'], id=sample['id'])
                self.log('CoWS starts: ' + sample_name)
                m = await cwspicarro.measure(sample_name, sampledata=sample, done_callback=self.finalize_isotopes)
                self.add_pcb(m.pcb_name(), m.progress)
                self.cwsmeasurement = m
                cwswaittask = asyncio.ensure_future(asyncio.sleep(60))
            # ************************************************
            # PHASE 6
            # Do throughflow measurements
            await self.__throughflow_measurement()

            # **************************************************
            # PHASE 7,8: Fill sample into fridge
            if tofridge:
                await self.__sample_to_fridge()

            # **************************************************
            self.phase += 1  # Save sample properties to db
            with session_scope() as session:
                osample = session.query(Sample).get(sample['id'])
                osample.storageid = sample.get('storageid')
                osample.addvalues(sourceid=source['id'])
                osample.ok = not cwspicarro
                trailer.loop.sample = osample.to_json()
            # Empty reservoir if cwspicarro is not available
            if not cwspicarro:
                await valvesystem.empty_complete()
            elif cwswaittask:
                try:
                    await cwswaittask
                except asyncio.CancelledError:
                    pass
            if self.conf.get('empty_source') and source.valveid in self.conf.empty_source:
                conf = self.conf.empty_source[source.valveid]
                self.log('Empty {} until {}<{:0.4g}'.format(source.name, conf.value, conf.until))
                await valvesystem.empty_source(source.valveid, conf.value, conf.until, conf.timeout)


        # Handle errors
        except TrailerException:
            self.finish()
            if self.cwsmeasurement and not self.cwsmeasurement.done():
                await self.cwsmeasurement.stop()

            raise
        except Exception as e:
            traceback.print_exc()
            self.finish()
            if self.cwsmeasurement and not self.cwsmeasurement.done():
                await self.cwsmeasurement.stop()
            raise TrailerException(repr(e), level=1, owner='measure')
        finally:
            # Everything done, reset the valvesystem
            await valvesystem.clear_command()
            if not cwspicarro:
                self.finish()


async def __measureisostandards(sample):
    """
    Standard measurements do only need the cws part of the measurement
    cycle and are handled differently than complete outdoor water samples.
    """

    # shortcuts to stuff
    sample = AttrDict(sample)
    source = sample.source
    cwspicarro = trailer.devices.get('cwspicarro')

    # Progress bar values
    pcb = trailer.progresscallbacks
    # check if call is valid
    if not cwspicarro:
        log(TrailerWarning('Standard measurement scheduled but no connection to CWS'))
        return
    if source.valveid not in [101, 102]:
        raise DeviceError('CWS Standard ports should be numbered as 101, 102', cwspicarro)

    # Wait for old measurement if necessary
    m = cwspicarro.measurement
    if m and not m.can_empty.is_set():
        __loglog('Wait for CWS client to be capable of new sample')
        time_to_go = m.time_to_switch
        pcb['Wait for: ' + m.pcb_name()] = lambda: (time_to_go - m.time_to_switch) / time_to_go
        try:
            await asyncio.wait_for(m.can_empty.wait(), timeout=1200)
        except asyncio.TimeoutError:
            raise DeviceError('CWS does not finish with {} after 20min'
                              .format(cwspicarro.measurement),
                              cwspicarro)
        finally:
            del pcb['Wait for: ' + m.pcb_name()]
    log(TrailerInfo('{name} started'.format(**sample)))
    # Start new measurement of standard
    __loglog('CWS: Start standard {}'.format(source.name))
    samplename = '{}(#{})'.format(source.name, sample.id)
    m = await cwspicarro.measure(samplename, source.valveid - 100, sampledata=sample, done_callback=saveisotopes)
    pcb[m.pcb_name()] = m.progress
    # Save sample time
    with session_scope() as session:
        osample = session.query(Sample).get(sample.id)
        osample.time = datetime.datetime.utcnow()

    # Wait until the sample is swallowed by the CWS (usually 3min)
    await asyncio.sleep(m.time_to_switch-60)


def check_disable(conf):
    """
    Checks the configuration if a measurement is possible. If there is anything against a measurement,
    raise a TrailerWarning giving the reasons
    :param conf: the measurement configuration
    :return: None
    """
    reasons = []
    if 'disable' in conf:
        for name, cond in conf.disable.items():
            try:
                happens = eval(cond, {}, trailer.devices.devicedata())
            except Exception as e:
                log(TrailerWarning('disable: checking {}:{} raised {!r}'.format(name, cond, e)))
                happens = False
            if happens:
                reasons.append(name)
    if reasons:
        raise TrailerWarning('Will not measure because it is ' + ', '.join(reasons))


class CleanFilter(asyncio.Task):
    """
    Cleans the filter by filling the reservoir with deionized water
    and then doing a backflush.
    """

    async def __clean_filter(self):
        cs = self.conf.clean_filter
        if not cs.repeat:
            return
        vs = trailer.devices.valvesystem
        pcb = trailer.progresscallbacks
        part = 0
        r = 0
        pcb.clean_filter = lambda: (r + part / 2 + vs.progress() / 2) / (cs.repeat + 2)
        await vs.empty_complete()
        for r in range(1, cs.repeat + 1):
            part = 0
            await vs.fill(cs.in_valve, cs.volume, wait=True)
            part = 1
            await vs.bempty(cs.out_valve, 20, wait=True)
        r += 1
        part = 0
        await vs.empty_complete()

    async def clean(self):
        if time_since_log('cleanfilter') > self.conf.clean_filter.timegap:
            # first wait for the picarro to release the reservoir
            cwspicarro = trailer.devices.get('cwspicarro')
            if cwspicarro and cwspicarro.measurement:
                await cwspicarro.measurement.can_empty.wait()
            else:
                await asyncio.sleep(30)
            try:
                await asyncio.wait_for(self.__clean_filter(), timeout=600)
            except TrailerException as e:
                log(e)
            except asyncio.TimeoutError:
                log(TrailerWarning('Cleaning filter took more than 10min', 'cleanfilter'))
            except Exception as e:
                traceback.print_exc()
                log(TrailerException('Clean filter raised {!r}'.format(e), level=1, owner='cleanfilter'))
            else:
                log(TrailerInfo('Filter cleaning successful', owner='cleanfilter'))
            finally:
                if 'clean_filter' in trailer.progresscallbacks:
                    del trailer.progresscallbacks['clean_filter']

    def __init__(self, conf):
        """
        :param conf: Measurement configuration
        :return:
        """
        self.conf = conf
        super().__init__(self.clean())


async def measure(sample):
    """
    Wraps the different kinds of sampling routines. When chasing problems this is the place to
    call special measurement coroutines
    :param sample: The actual sample, represented by a Mapping
    :return:
    """
    sample = AttrDict(sample)
    source = sample.source
    conf = get_config().measure
    check_disable(conf)
    if source.valveid in range(100):
        m = __LiquidMeasurement(sample, conf)
        await m.run()

    elif source.valveid in [101, 102]:
        clean_task = None
        # While std 1 is measured, clean the filter with
        # water, using the backflush (bempty)
        if source.valveid == 101 and 'clean_filter' in conf:
            clean_task = CleanFilter(conf)
        # Isotopic standard sampling

        await __measureisostandards(sample)
        if clean_task:
            await clean_task


