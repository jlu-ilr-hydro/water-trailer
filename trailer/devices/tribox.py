#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tribox controller application of the icon machine.
Create an instance of System to start it


Author: Philipp Kraft

TODO: Fit to modbusClient, rethink of ordering (devices etc.)
"""
from math import isfinite
import time
import asyncio
from attrdictionary import AttrDict
import traceback
from datetime import timedelta

from .base import Device
from . import DeviceError

from .modbus.umodbus import uMaster as MdbMaster
# pylint: line-too-long

debug = False


def is_float(v):
    """
    Helper function, checks if v is a float
    """
    try:
        f = float(v)
    except:
        return False
    else:
        return True


class TriboxError(Exception):
    pass


class TriOSdevice(object):
    """This class encapsulates common parts of the modbus
    interface to TriOS devices"""
    def __init__(self, client, unit):
        """
        This class encapsulates common parts of the modbus
        interface to TriOS devices
         - client - a modbus client
         - unit   - The unit (slave) number of the device
        """
        self.client = client
        self.unit = unit
        self.name = 'unknown'

    def __str__(self):
        return self.name

    async def values(self):
        """Returns a generator object to iterate of the measured values
        list(device.values()) returns a list of name,value,unit tuples
        """
        res = []
        for i in range(32):
            value = await self.client.readfloat32(1000 + i * 2, self.unit)
            name = await self.client.readstring(1064 + i * 10, 20, self.unit)
            unit = await self.client.readstring(1384 + i * 10, 20, self.unit)
            if name:
                res.append((name, value, unit))
            else:
                break
        return res
    async def fixed_name(self):
        resp=await self.client.readstring(20, 40, self.unit)
        self.name = resp.strip('\0')
        return self.name

class Tribox(TriOSdevice):
    """A high-level API wrapping the modbus interface of the Tribox2 device
    Usage:
    host_ip = '192.168.0.5'
    tribox = Tribox(host_ip)
    result = tribox.measure()
    """
    def __init__(self, master):
        """A high-level API wrapping the modbus interface of the Tribox2 device
         - host The IP address of network name of the device
         - port The port number for the modbus connection (usually 502)
        """
        client = master
        super().__init__(client, 1)

    async def measure(self):
        "Triggers a measurement and returns the measured values"
        # Modbus signal to trigger measurement
        await self.client.writecoil(1, unit=self.unit)
        
    async def setname(self, newname):
        "Sets the device name"
        # pad name with 0x0
        newname = newname[:64] + '\0' * (64 - len(newname))
        await self.client.writestring(108, newname, self.unit)

    async def getname(self):
        "Gets the device name"
        return await self.client.readstring(108, 64, self.unit)


    async def getserialnumber(self):
        return await self.client.readint32(100, self.unit)

    def __repr__(self):
        return "Tribox2 ({})".format(self.client.host)

    async def get_time(self):
        return await self.client.readtime(101, self.unit)

class ProPS(TriOSdevice):

    def __init__(self, tribox, unit=2):
        super().__init__(tribox.client, unit)

    async def measure(self):
        await self.client.writecoil(0, True, unit=self.unit)

    async def pathlength(self):
        return await self.client.readshort(100, unit=self.unit)

    async def number_of_averaged_measurements(self):
        return await self.client.readshort(101, self.unit)


class LSA(TriOSdevice):
    """The Linear Substance Analyser. Calculates the concentrations from the
    measured spectra"""
    def __init__(self, tribox, unit=20):
        super().__init__(tribox.client, unit)

    async def get_measure_time(self):
        try:
            return await self.client.readtime(40, self.unit)
        except ValueError:
            return None

    async def get_number_of_conc_values(self):
        return await self.client.readshort(47, self.unit)


class TriboxDevice(Device):
    """
    An asyncio solution to do measurements with the ProPS/LSa on a tribox
    """
    name = 'tribox'
    def __init__(self, host, port=502, ProPSunit=2, LSAunit=20, active=True, **kwargs):
        self.client = MdbMaster(host, port)
        self.tribox = Tribox(self.client)
        self.props = ProPS(self.tribox, unit=ProPSunit)
        self.lsa = LSA(self.tribox, unit=LSAunit)
        self.active = True
        self.lock = asyncio.Lock()
        self.readtime = 0.0
        super().__init__()
        self.active = active

    def __str__(self):
        return '{self.tribox}({self.props},{self.lsa})'.format(self=self)
    
    async def measure(self):
        """
        Performs a ProPS measurement and returns an attrdict with the data items
        :return:
        """
        self.is_ready.clear()
        if debug:
            print('tribox: start measure')
        if self.active:
            async with self.lock:
                # Get the last time of an LSA measurement
                old_lsa_time = await self.lsa.get_measure_time()
                if debug:
                    print('tribox: lsa time:', old_lsa_time)
                # Clear ready flag
                self.is_ready.clear()
                if debug: print(old_lsa_time)
                if debug: print('tribox: do ProPS measure')

                # Do the measurement
                await self.props.measure()
                self.errors = []
            if debug:
                print('tribox: await result')
            # Wait for LSA result (up to 60s)
            for _ in range(120):
                # Read the LSA time
                new_lsa_time = await self.lsa.get_measure_time()
                # If the LSA time has changed, we got a new measurement
                if new_lsa_time != old_lsa_time:
                    if debug:
                        print('tribox: got result, new lsa time:', new_lsa_time)
                    # set ready flag and break repeat loop
                    self.is_ready.set()
                    await self.readstatus()
                    # Handle the new result
                    return self, AttrDict((k, float(v)) for k, v in self.data.items() if is_float(v))
                await asyncio.sleep(0.5)
            # If the for loop did not return after 120 tries a 0.5sec
            # something's wrong with the tribox or the LSA
            raise DeviceError('tribox: No result from LSA', self)

    async def readstatus(self):
        """
        Reads the status from the Tribox

        :return:
        """
        if self.lock.locked():
            return self
        async with self.lock:
            self.data['triboxtime'] = await self.tribox.get_time()
            t = self.data['lsatime'] = await self.lsa.get_measure_time()
        self.readtime = time.time()

        # clean errors
        self.errors = []
        # Read tribox data
        async with self.lock:
            pp_values = await self.props.values()
            lsa_values = await self.lsa.values()
        signal_200nm = pp_values[3][1]
        bubbles = pp_values[2][1]
        lamp_intens = pp_values[0][1]
        if bubbles > 0.0:
            self.errors.append("Bubbles detected! ({:0.3g})".format(bubbles))
        if signal_200nm < 1.5 or signal_200nm > 2.5:
            self.errors.append("Change pathlength!")
        if lamp_intens < 50.0:
            self.errors.append("Low lamp intensity of {:0.1f}".format(lamp_intens))

        self.data.update(AttrDict((v[0].replace(' ','_').replace('-', '_'),
                                   v[1] if isfinite(v[1]) else None)
                                   for v in pp_values + lsa_values))
        self.readtime = time.time()
        
        return self
   
async def create(name, conf):
    """
    Creates and checks a TriboxDevice
    
    takes <1s
    """

    dev = TriboxDevice(**conf)
    dev.name = name

    def cancel(coros):
        for c in coros:
            c.cancel()
    get_names = [asyncio.ensure_future(subdev.fixed_name())
                 for subdev in (dev.tribox, dev.props, dev.lsa)]
    names = []
    while get_names:
        coro = get_names.pop(0)
        try:
            names.append(await coro)
        except asyncio.TimeoutError:
            cancel(get_names)
            raise DeviceError('Communication with tribox took more than 10s', 'Tribox')
        except OSError:
            cancel(get_names)
            raise DeviceError('Communication error with tribox on {}:{}. {} were ok'
                              .format(conf.host, conf.port, ', '.join(names) if names else 'None'),
                              'Tribox')
        except:
            cancel(get_names)
            traceback.print_exc()
            raise DeviceError('Communication error with tribox on {}:{}. {} were ok'
                              .format(conf.host, conf.port, ', '.join(names) if names else 'None'),
                              'Tribox')
    await dev.handle_conf_event('on_create', conf)
    return dev
                
    

