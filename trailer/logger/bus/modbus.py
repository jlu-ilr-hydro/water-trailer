import asyncio
import json

from umodbus.client import tcp

import trailer.logger.bus.base as base


class Sensor(base.Sensor):
    def __init__(self, mdbunit, startaddress, length, name=None, **kwargs):
        self.mdbunit = mdbunit
        self.name = name
        self.valuefactories = []
        self.extradata = kwargs
        self.startaddress = startaddress
        self.length = length

    def __repr__(self):
        return ('{}.Sensor(mdbunit={self.mdbunit}, startaddress={self.startaddress}, ' +
                'length={self.length}, name={self.name})').format(__name__, self=self)

    def __str__(self):
        return '{} (unit={}) ({} values)'.format(self.name, self.mdbunit, len(self.valuefactories))

    def __asdict__(self)->dict:
        res = self.extradata.copy()
        res.update(dict(mdbunit=self.mdbunit, name=self.name,
                        startaddress=self.startaddress, length=self.length,
                        values=[]))
        for vf in self.valuefactories:
            res['values'].append(vf.__asdict__())
        return res

    @classmethod
    def from_dict(cls, data: dict):
        values = data.pop('values', [])
        res = cls(**data)
        for v in values:
            res.valuefactories.append(base.ValueFactory.from_dict(v))
            res.valuefactories[-1].name = res.name + '.' + res.valuefactories[-1].name
        return res


async def send_message(adu, reader, writer):
    """
    Sends a adu message to the tcp client writer/reader pair
     - reader and write are created with asyncio.open_connection
     - the adu is a mdb message
    """
    writer.write(adu)
    await writer.drain()
    response = await reader.read(1024)
    return tcp.parse_response_adu(response, adu)


class Bus(base.Bus):
    def __init__(self, host, port=512, **kwargs):
        self.client = (host, port)
        self.extradata = kwargs
        self.sensors = []

    def __asdict__(self):
        res = self.extradata.copy()
        res.update(dict(host=self.client[0], port=self.client[1]))
        res['module'] = __name__
        res['sensors'] = []
        for s in self.sensors:
            res['sensors'].append(s.__asdict__())
        return res

    @classmethod
    def from_dict(cls, data: dict):
        sensors = data.pop('sensors', [])
        bus = cls(**data)
        for s in sensors:
            bus.sensors.append(Sensor.from_dict(s))
        return bus

    def __str__(self):
        return 'ModbusTCP client on {} with {} sensors'.format(self.client[0], len(self.sensors))

    async def readsensor(self, sensor: Sensor):
        """
        Reads a single sensor
        """
        r, w = await asyncio.open_connection(*self.client)
        msg = tcp.read_holding_registers(sensor.mdbunit, sensor.startaddress, sensor.length)
        resp = await send_message(msg, r, w)
        w.close()
        
        return [vf(resp[vf.id-sensor.startaddress]) for vf in sensor.valuefactories]

    async def read_all(self):
        values = []
        for sensor in self.sensors:
            s_values = await self.readsensor(sensor)
            values.extend(s_values)
        return values

    def sensors_from_csv(self, filename):
        """
        Creates sensors from a csv file with the columns:
        unit (slave_id), name, description, address, typename, scalefactor, unit
        :param filename: tge filename
        :return:
        """
        slave_id = None
        with open(filename) as f:
            for line in f:
                if line.strip().startswith('#'):
                    continue
                ls = line.split(',', 6)
                if ls[0].strip() != str(slave_id):
                    try:
                        slave_id = int(ls[0].strip())
                    except (ValueError, TypeError):
                        continue
                    address = int(ls[3])
                    self.sensors.append(Sensor(slave_id, address, 0))
                s = self.sensors[-1]
                # Add a value to the sensor
                s.length += 1
                # 1 name, 2 description, 3 address, 4 typename, 5 scalefactor, 6 unit
                name = ls[1].strip()
                unit = ls[6].strip()
                id = int(ls[3].strip())
                # Get the scale function. When the unit is wrapped by braces, assume a lookup dict in the unit
                if unit.strip().startswith('{') and unit.strip().endswith('}'):
                    scalefunction = base.ScaleFunction(unit.strip() + '[x]', testvalue=None)
                    unit = ''
                elif ls[5]:
                    scalefunction = base.ScaleFunction('x / ' + ls[5].strip())
                else:
                    scalefunction = None

                vf = base.ValueFactory(name=name, unit=unit,
                                       scalefunction=scalefunction,
                                       id=id, description=ls[2].strip())
                s.valuefactories.append(vf)
