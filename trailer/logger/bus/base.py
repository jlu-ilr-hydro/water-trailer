from datetime import datetime
import importlib
from trailer import to_yaml, from_yaml

class Bus:
    """
    Base class for a generic bus system.
    General hierachy of the logger system:
    Bus (eg. SDI12)
    -->has sensors (eg. VAISALA @ address 0)
       -->has valuefactories (eg. Air Temp)
    """
    def __asdict__(self):
        raise NotImplementedError

    async def makesensor(self, **kwargs):
        raise NotImplementedError

    async def readsensor(self, sensor):
        raise NotImplementedError

    async def read_all(self):
        """
        Reads all sensors
        :return: A List of Values
        """
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict):
        """
        Loads a bus from a dictionary (eg. given by JSON or YAML).
        The bus type is loaded from the module key of the dictionary
        :param data: The dictionary describing the bus
        :return: module.Bus, where module is the module given in data['module']
        """
        if 'module' not in data:
            raise KeyError('To create a generic logger.Bus you need to provide the module')
        modname = data.pop('module')
        try:
            module = importlib.import_module(modname)
        except Exception:
            raise ValueError('Module "{}" not found, check configuration'.format(modname))
        if 'Bus' not in vars(module):
            raise KeyError('Module "{}" exists, but has no class Bus'.format(modname))
        return module.Bus.from_dict(data)

    @classmethod
    def from_file(cls, busfile):
        """
        Loads a Bus from a description file
        :param busfile: Filename of the yaml description of the bus
        :return: the bus
        """
        data = from_yaml(busfile)
        return cls.from_dict(data)

    def to_file(self, busfile):
        """
        Saves the current bus description as a yaml file
        :param busfile: Filename to save. For further use, the file should match to: preferences/*.bus.yaml
        """
        to_yaml(self.__asdict__(), busfile)

    def to_stream(self, stream):
        to_yaml(self.__asdict__(), stream)


class Sensor:
    """
    Base class for a sensor on a bus
    """
    pass


class ScaleFunction:
    """
    A user defined function to scale or translate a measured value into something meaningful
    """

    def __init__(self, code: str, testvalue=None):
        if 'x' not in code:
            raise ValueError('Function code {} must include the variable x'.format(code))
        self.__code = code
        try:
            import math
            self.function = eval('lambda x:' + code, vars(math))
            if testvalue is not None:
                self.function(testvalue)
        except Exception as e:
            raise ValueError('f(1) = {} is not a valid python expression, got error: {}'
                             .format(code.replace('x', '1'), repr(e)))

    def __call__(self, x: float):
        return self.function(x)

    def __repr__(self):
        return "ScaleFunction('{}')".format(self.__code)

    def __str__(self):
        return self.__code


class ValueFactory:
    """
    A value factory is a kind of template to create a value with all needed metadata
    """

    def __init__(self, name=None, unit=None, datasetid=None, scalefunction=None, id=None, **kwargs):
        """

        :param name: Name of the measured item
        :param unit: Unit of the measured item
        :param datasetid: Target datasetid in external database eg. Schwingbach
        :param scalefunction: A valid python expression to transform the raw data into the output value
        :param id: Identifyer of the valuetype
        :param kwargs: Extraarguments passed to the Value
        """
        self.name = name
        self.unit = unit
        self.datasetid = datasetid
        if isinstance(scalefunction, ScaleFunction):
            self.scalefunction = scalefunction
        elif scalefunction:
            self.scalefunction = ScaleFunction(scalefunction)
        else:
            self.scalefunction = None
        self.id = id
        self.extradata = kwargs

    def __asdict__(self) ->dict:
        """
        Creates a dict describing te
        :return:
        """
        res = self.extradata.copy()
        res.update(dict(name=self.name, unit=self.unit, datasetid=self.datasetid,
                        scalefunction=str(self.scalefunction) if self.scalefunction else None,
                        id=self.id))
        return res

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

    def __call__(self, value, time=None, **kwargs):
        """
        Creates a Value from a float
        :param value: the measured value
        :param time: A datetime of the measurement, if None, utcnow() is used
        :param kwargs: Extra meta data to be stored with the value
        :return: Value
        """
        if self.scalefunction:
            value = self.scalefunction(value)
        time = time or datetime.utcnow()
        data = self.extradata.copy()
        data.update(kwargs)
        return Value(value, time, self.name, self.datasetid, unit=self.unit, **data)

    def __repr__(self):
        if self.scalefunction:
            name = str(self.scalefunction).replace('x', self.name)
        else:
            name = self.name
        return '{name} (id:{self.id}) [{self.unit}]->ds:{self.datasetid}'.format(name=name, self=self)


class Value:
    """
    A measured value with metadata
    """
    def __init__(self, value, time=None, name=None, datasetid=None, unit=None, **kwargs):
        """
        Creates the value with meta data
        :param value: The value (a float)
        :param time: Time of measurement
        :param name: Name of measurement
        :param datasetid: Target dataset id in external database (eg- Schwingbach)
        :param kwargs: Additional meta data
        """
        self.value = value
        self.name = name
        self.time = time
        self.datasetid = int(datasetid) if datasetid else None
        self.unit = unit
        self.extradata = kwargs

    def __str__(self):
        res = ''
        if self.name:
            res += self.name + '='
        res += '{:0.6g}'.format(self.value)
        if hasattr(self, 'unit') and self.unit:
            res += ' ' + str(self.unit)
        if self.time:
            res += self.time.strftime(' (%d.%m.%Y %H:%M:%S)')
        if self.datasetid:
            res += ' ->ds:' + str(self.datasetid)
        return res

    def __repr__(self):
        res = 'name={name!r}, time={time!r}, value={value:0.4g}, datasetid={datasetid}'.format(**vars(self))
        if self.extradata:
            res += ', ' + ', '.join('{!s}={!r}'.format(*it) for it in self.extradata.items())
        return 'Value({})'.format(res)

    def __asdict__(self):
        """
        :return: The Value as a dictionary
        """
        res = self.extradata.copy()
        res.update(dict(name=self.name, value=self.value, time=self.time.isoformat(), datasetid=self.datasetid))
        return res
