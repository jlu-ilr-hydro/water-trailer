'''
Created on 21.03.2016

@author: kraft-p
'''

import struct
from datetime import datetime

import umodbus.client.tcp as utcp 
import asyncio



class uMaster(object):
    """
    The MdbMaster wrap
    """

    def __init__(self, host, port):
        """
        Defines a new master for a modbus tcp device
        """
        self.host = host
        self.port = port
        self.reader, self.writer = None, None
        self.lock = asyncio.Lock()

    async def send_message(self, adu):
        """
        Sends a adu message to the tcp client writer/reader pair
         - reader and write are created with asyncio.open_connection
         - the adu is a mdb message
        """
        if self.writer is None:
            self.reader, self.writer = await asyncio.open_connection(self.host,self.port)
        self.writer.write(adu)
        await self.writer.drain()
        response = await self.reader.read(1024)
        return utcp.parse_response_adu(response, adu)
        
    async def readraw(self, address, length=1, unit=1):
        """Read a byte string from the holding registers of a modbus device.
         - address The starting address of the string register
         - length The length of the string in the register
         - unit The unit number of the modbus device
        returns a string
        """
        count = int(length) // 2 + int(length) % 2
        msg = utcp.read_holding_registers(unit, address - 1, count)
        async with self.lock:
            resp = await self.send_message(msg) 
        return struct.pack('<' + 'H' * count, *resp)

    async def readstring(self, address, length, unit=1):
        """Read a string from a modbus device and check for null termination
         - client A modbus client 
         - unit The unit number of the modbus device 
         - address The starting address of the string register
         - length The length of the string in the register
        """

        bresult = await self.readraw(address, length, unit)
        result = bresult.decode()
        if '\0' in result:
            return result[:result.index('\0')].strip()
        else:
            return result.strip()

    async def readint32(self, address, unit=1):
        """Read a 32 bit integer from a modbus device
         - address The starting address of the string register
         - unit The unit number of the modbus device 
         return an integer
        """
        result = await self.readraw(address, 4, unit)
        return struct.unpack('<i', result)[0]

    async def readfloat32(self, address, unit=1):
        """Read a 32 bit floating point number from a modbus device
         - address The starting address of the string register
         - unit The unit number of the modbus device 
        """
        result = await self.readraw(address, 4, unit)
        return struct.unpack('<f', result)[0]

    async def readfloat64(self, address, unit=1):
        """Read a 64 bit floating point number from a modbus device
         - address The starting address of the string register
         - unit The unit number of the modbus device
        """
        result = await self.readraw(address, 8, unit)
        return struct.unpack('<d', result)[0]

    async def readtime(self, address, unit=1):
        msg = utcp.read_holding_registers(unit, address, 6)
        async with self.lock:
            resp = await self.send_message(msg)
        try:
            return datetime(*resp)
        except ValueError:
            raise ValueError(
                "Could not interprete sequence %s as [year,month,day,hour,minute,second]" % resp)

    async def readshort(self, address, unit=1):
        msg = utcp.read_holding_registers(unit, address, 1)
        async with self.lock:
            resp = await self.send_message(msg)
        return resp

    async def readtype(self, typename, address, unit=1):
        typehandlerdict = {
            'int16': self.readshort,
            'uint16': self.readraw,
            'datetime': self.readtime,
            'int32': self.readint32,
            'float32': self.readfloat32,
            'float64': self.readfloat64,
        }
        return typehandlerdict[typename](unit, address)

    async def writestring(self, string, address, unit=1):
        """Writes a string from a modbus device. 
         - client A modbus client 
         - unit The unit number of the modbus device 
         - address The starting address of the string register
         - result The string to write
        """
        bstr = string.encode('utf-8')
        count = len(bstr) // 2 + len(bstr) % 2
        values = struct.unpack('<' + 'H' * count, bstr)
        msg = utcp.write_multiple_registers(unit, address, values)
        async with self.lock:
            return await self.send_message(msg)

    async def writecoil(self, address, value=True, unit=1):
        """
        Writes a single coil on the modbusdevice
        """
        if value:
            value = 0xFF00
        else:
            value = 0x0000
        msg = utcp.write_single_coil(unit, address, value)
        async with self.lock:
            return await self.send_message(msg)

