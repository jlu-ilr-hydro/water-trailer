"""
Logger bus wrapper for SDI12 devices

SDI12 specification: http://www.sdi-12.org/current%20specification/SDI-12_version-1_4-August-10-2016.pdf
"""
from . import base
from trailer.devices import aioserial
import asyncio
import datetime
from orderedattrdict import AttrDict


import warnings


def encode(string: str) -> bytes:
    """
    Encodes a unicode string to a bytesting with UTF-8
    :param string:
    :return:
    """
    return string.encode()


def decode(bytestring: bytes) -> str:
    """
    Decodes a bytestring to unicode assuming UTF-8
    :param bytestring:
    :return:
    """
    return bytestring.decode()


class parser:
    """
    Helper functions to parse SDI12 responses
    """
    channels = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'

    @staticmethod
    def M(response):
        """
        Parses the response to a C or M command
        :return: time to result, number of values
        """
        try:
            return int(response[1:4]), int(response[4:])
        except (ValueError, TypeError):
            raise RuntimeError('Expected numbers but got {}'.format(response))

    @staticmethod
    def D(response):
        """
        Parses the response to an SDI12 D command and yields the values
        :param response: Typical response to D command is a+xxx.x+xxx.xxx-xxx
        :return: List of float values
        """
        # Add spaces between the numbers, split the response and skip the address
        values = response.replace('+', ' +').replace('-', ' -').split()[1:]
        for value in values:
            try:
                v = float(value)
                yield v
            except (ValueError, TypeError):
                yield None


class Sensor(base.Sensor):
    """
    Wraps a sensor on a SDI12-Bus connected over the Arduino based
    SDI12 connector
    """

    def __init__(self, channel, name, **kwargs):
        """
        Creates a new SDI12device from the response to the aI! string
        :bus: the SDI12bus this device belongs to.
        :info: A string line response from the SDI12 aI! command
        :config: A list of dictionaries
        """
        self.channel = channel
        self.name = name
        self.valuefactories = []
        self.extradata = AttrDict(kwargs)

    def __str__(self):
        return ('SDI12 device on {o.channel} is {o.name} ({c} values)'
                .format(o=self, c=len(self.valuefactories)))

    async def doD(self, write, wait, nvalues):
        """
        Wait the wait time and performs the D0 (get data) command
        If necessary it calls also the D1, D2 etc commands
        :param write: Write coroutine
        :param wait: Wait time in seconds
        :param nvalues:
        :return:
        """
        tstart = datetime.datetime.utcnow()
        await asyncio.sleep(wait)
        # Get the values, probably spread over several D commands
        floatvalues = []
        d = 0  # The D command number
        # repeat the D commands as necessary
        while len(floatvalues) < nvalues:
            response = await write('{}D{}!\r\n'.format(self.channel, d))
            floatvalues.extend(parser.D(response))
            d += 1
        # Augment & transform the values
        return [factory(x, time=tstart) for
                factory, x in
                zip(self.valuefactories, floatvalues)]

    def __asdict__(self)->dict:
        res = self.extradata.copy()
        res.update(dict(channel=self.channel, name=self.name, values=[]))
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


class Bus(base.Bus):
    """
    Wraps the COMport for communication with the devices
    """

    def __init__(self, port, **kwargs):
        self.port = port
        self.baudrate = 9600
        self.timeout = 0.5
        self.lock = asyncio.Lock()
        self.extradata = kwargs
        self.sensors = []
        self.serial = aioserial.Ser2Net(device=port)
        self.debug = False

    def __repr__(self):
        return 'sdi12.Bus(port={})'.format(self.port)

    def makesensor(self, channel, name=None, values=None, **kwargs) -> Sensor:
        """
        Create a sensor on this bus
        :param channel: SDI12 channel ('0'..'9', 'a'..'z','A'..'Z')
        :param name: Name of the sensor
        :param values: List of dict, describing valuefactories
        :param kwargs: Extra data to describe the sensor
        :return: The created SDI12Sensor
        """
        s = Sensor(channel, name, **kwargs)
        if values:
            errors = []
            for v in values:
                try:
                    s.valuefactories.append(base.ValueFactory(**v))
                except Exception as e:
                    errors.append(e)
                else:
                    errors.append(None)
                    # TODO: Do something about the errors
        return s

    def __asdict__(self):
        res = self.extradata.copy()
        res.update(dict(port=self.port))
        res['module'] = __name__
        res['sensors'] = []
        for s in self.sensors:
            res['sensors'].append(s.__asdict__())
        return res

    @classmethod
    def from_dict(cls, data: dict):
        data.pop('module', None)
        sensors = data.pop('sensors', [])
        bus = cls(**data)
        for s in sensors:
            bus.sensors.append(Sensor.from_dict(s))
        return bus

    async def open(self):
        """
        Opens the serial port and drains the port
        :return:
        """
        await self.serial.open()
        try:
            await self.serial.read(1024)
        except asyncio.TimeoutError:
            pass

    async def write(self, cmd: str) -> str:
        """
        Writes string cmd to serial port and return the response as string
        :param cmd:
        :return:
        """
        with await self.lock:
            if self.debug:
                print('Writing ', cmd.strip(), ' to ', self.port)
            await self.serial.write(encode(cmd + '\n'))
            # SDI 12 is slow, llet some time pass until looking for a result
            await asyncio.sleep(0.1)
            line = await self.serial.readline()
            return decode(line)

    async def scanbus(self, channels=parser.channels):
        """
        Scans the SDI12 bus on the channels and creates sensor stubs
        :param channels: A string of channel characters
        :return: None
        """

        for channel in channels:
            if self.debug:
                print('Channel: ', channel, end='\n')
            # Check channel with Acknowledge Active Command
            response = await self.write(channel + '!\r\n')
            if response.strip() == channel:
                if self.debug:
                    print('ok')
                name = (await self.write(channel + 'I!\r\n')).strip()
                if self.debug:
                    print('Found', name, 'at channel', channel)
                s = self.makesensor(channel, name[1:])
                # Get number of values with C command to add valuefactories
                response = await self.write(channel + 'C!\r\n')
                wait, nvalues = parser.M(response)
                # Add valuefactories
                for i in range(nvalues):
                    s.valuefactories.append(base.ValueFactory(name='Value_{:02d}'.format(i), id=i))
                if self.debug:
                    print(name, 'has', nvalues, 'values and takes', wait, ' seconds')
                self.sensors.append(s)
            elif response.strip():
                warnings.warn('Queried channel {} but got {} as answer'.format(channel, response.strip()))
        
    async def read_all(self):
        """
        Reads all sensors concurrently
        :return:
        """
        return await self.readsensor(*self.sensors)

    async def readsensor(self, *sensors):
        """
        Reads the given sensor(s)
        :param sensors: SDI12 sensor objects
        :return: List of Value objects created by the sensors valuefactories
        """

        # Storages for wait and value numbers
        wait_list = []
        nvalue_list = []

        # Send measurement command to each sensor
        for s in sensors:
            response = await self.write(s.channel + 'C!\r\n')
            # get wait time and number of values for this device
            wait, nvalues = parser.M(response)
            if self.debug:
                print('{} values in {}s for {}'.format(nvalues, wait, s))
            wait_list.append(wait)
            nvalue_list.append(nvalues)

        # Get the data from the sensors
        values = await asyncio.gather(*[s.doD(self.write, w, n) for
                                        s, w, n in
                                        zip(sensors, wait_list, nvalue_list)])
        return sum(values, [])  # slow but acceptable way to flatten list of lists
