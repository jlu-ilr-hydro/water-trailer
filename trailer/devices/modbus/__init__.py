
class ModbusReadException(Exception):
    "An exception for reading errors on modbus devices"

    def __init__(self, client, unit, address, count):
        if count > 1:
            msg = 'Could not read registers %i to %i from unit %i at client %s' % \
                (address + 1, address + count, unit, client)
        else:
            msg = 'Could not read registers %i from unit %i at client %s' % \
                (address + 1, unit, client)
        super(ModbusReadException, self).__init__(msg)


class ModbusWriteException(Exception):
    "An exception thrown at writing errors on modbus devices"

    def __init__(self, client, unit, address, count):
        super(ModbusWriteException, self).__init__()
        if count > 1:
            msg = 'Could not write registers %i to %i from unit %i at client %s' % \
                (address + 1, address + count, unit, client)
        else:
            msg = 'Could not write registers %i from unit %i at client %s' % \
                (address + 1, unit, client)
        super(ModbusWriteException, self).__init__(msg)

