
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wrapping the TCP interface of the PICARRO analyzer

Source: Picarro Analyzer Programming Guide - Remote Command Interface
        Revision 2.0, 2010, Picarro Inc.


Created on May 25, 2011
@author: Philipp Kraft
"""
import asyncio


import time

from . import Device, DeviceError, DeviceWarning

class Picarro(Device):
    """ A class for communictation with the picarro
    """
    def __init__(self, host=None, port=None):
        super().__init__()
        self.host = host
        self.port = port or 51020
        self.lock = asyncio.Lock()
        self.refreshrate = 1.0

    def __str__(self):
        return 'Picarro L2130-i'

    async def execute(self, command):
        # complete the command
        if not command.endswith(chr(13)):
            command += chr(13)
        response = None
        await asyncio.sleep(0.01)
        with await self.lock:
            reader, writer = await asyncio.open_connection(host=self.host, port=self.port)
            try:
                writer.write(command.encode())
                await writer.drain()
                response = await reader.readline()
            finally:
                writer.close()

        return response.decode()


    async def readstatus(self):

        self.readtime = self.data.time = time.time()
        # get status
        resp = await self.execute("_Instr_GetStatus")
        try:
            status = int(resp)
        except ValueError:
            raise DeviceError('Picarro answered %s on "_Instr_GetStatus", not an int' % resp, self)
        flags = {1: 'Ready', 2: 'Meas Active', 4: 'Error in buffer', 64: 'Gas Flowing',
                 128: 'Pressure locked', 256: 'Cavity temp locked', 512: 'Warm box locked',
                 8192: 'Waming up', 16384: 'System Error'}
        self.data.status = ', '.join([flag for n, flag in flags.items() if status & n])
        # get scantime
        resp = await self.execute('_Meas_GetScanTime')
        try:
            self.data.scantime = float(resp)
        except (ValueError, TypeError):
            raise DeviceWarning('picarro.scantime(): Got not a float but %s, using 2s instead' % resp, self)
        # get data
        resp = await self.execute("_Meas_GetConcEx")
        if resp:
            if resp.startswith('ERR:'):
                if "3001" in resp:
                    raise DeviceWarning('Measurement system disabled, instrument state: %s' %
                                        ', '.join(self.status()), self)
                elif "3002" in resp:
                    raise DeviceWarning('No measurement data exists, instrument state: %s' %
                                        ', '.join(self.status()), self)
                else:
                    raise DeviceError('picarro.get_result: Unknown error "%s", instrument state: %s' %
                                      (resp, self.data.status), self)
            else:
                rl = resp.split(';')
                try:
                    result = [float(r) for r in rl[1:] if r.strip()]
                    self.data.H2O, self.data.d18O, self.data.d2H = result[:3]
                except ValueError:
                    raise DeviceError('Cannot parse "%s" as list of floats', self)
        else:
            raise DeviceWarning('picarro.get_result: Could not talk to picarro, try next time', self)

        self.data.readtime = time.time() - self.data.time
        return self

async def create(name, conf):
    pic = Picarro()
    pic.apply_config(conf)
    pic.name = name
    try:
        await asyncio.wait_for(pic.readstatus(), timeout=5)
    except asyncio.TimeoutError:
        raise DeviceError('Initial communication with picarro took more than 5s', pic)
    else:
        await pic.handle_conf_event('on_create', conf)
    return pic
