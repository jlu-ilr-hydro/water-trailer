from orderedattrdict import AttrDict
import asyncio

from trailer.devices import aioserial
from . import base


class MayaException(Exception):
    pass


def parse_inputs(line, value_count):
    hex_index = line.index('0x')
    hex_val = int(line[hex_index:hex_index+4], 0)
    return [hex_val] * value_count


def parse_gps(line, value_count):
    ls = line.split(',')
    return [float(x) for x in ls[1:6:2]]


def parse_float(line, value_count):
    ls = line.split(',')
    val = ls[-1].split('-')[0]
    return [float(val)] * value_count



class Sensor(base.Sensor):

    parsers = {'gps': parse_gps,
               'inputs': parse_inputs,
               'vpwr': parse_float,
               'brdtmp': parse_float,
               'vign': parse_float}

    def __init__(self, name, command):
        self.name = name
        self.valuefactories = []
        self.command = command

    def __repr__(self):
        return 'MajaSensor({},{})'.format(self.name,self.command)

    def __str__(self):
        return 'maja: ?{} -> {}'.format(self.command, self.name)

    def parse_line(self, line):
        if self.command in self.parsers:
            return self.parsers[self.command](line, len(self.valuefactories))

    async def read(self, serial: aioserial.Ser2Net):
        cmd = ('?' + self.command + '\r\n').encode()
        await serial.write(cmd)
        line = await serial.readline()
        line = line.decode()
        if line.strip() == 'error':
            raise MayaException('Expected answer to ?{}, got error', self.command)
        line2 = (await serial.readline()).decode()
        if not line2.strip() == 'ok':
            raise MayaException('got text "{}" but not an ok'.format(line))
        values = self.parse_line(line)
        return [vf(x) for vf, x in zip(self.valuefactories, values)]

    def __asdict__(self)->AttrDict:
        res = AttrDict(command=self.command, name=self.name, values=[])
        for vf in self.valuefactories:
            res.values.append(vf.__asdict__())
        return res

    @classmethod
    def from_dict(cls, data: AttrDict):
        values = data.pop('values', [])
        res = cls(**data)
        for v in values:
            res.valuefactories.append(base.ValueFactory.from_dict(v))
            res.valuefactories[-1].name = res.name + '.' + res.valuefactories[-1].name
        return res



class Bus(base.Bus):
    def __init__(self, port):
        self.port = port
        self.sensors = []
        self.serial = aioserial.Ser2Net(port, timeout=0.3)

    def __repr__(self):
        return 'maja.Bus(port={})'.format(self.port)

    async def readsensor(self, sensor):
        await self.serial.open()
        try:
            return await sensor.read(self.serial)
        finally:
            self.serial.close()

    async def read_all(self):
        values = []
        await self.serial.open()
        try:
            for sensor in self.sensors:
                res = await sensor.read(self.serial)
                values.extend(res)
            return values
        finally:
            self.serial.close()

    def __asdict__(self):
        res = AttrDict(port=self.port)
        res.module = __name__
        res.sensors = [s.__asdict__() for s in self.sensors]
        return res

    @classmethod
    def from_dict(cls, data: dict):
        data.pop('module', None)
        sensors = data.pop('sensors', [])
        bus = cls(**data)
        for s in sensors:
            bus.sensors.append(Sensor.from_dict(s))
        return bus


