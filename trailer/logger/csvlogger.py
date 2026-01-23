"""

"""

import os

# Get BOM for excel csv


class Csv:
    def __init__(self, filename, openmode='a'):
        if (not os.path.exists(filename)) or openmode == 'w':
            self.file = open(filename, 'w')
            # Make Excel aware this is UTF-8 coded (BOM)
            self.file.write('\ufeff')
            # Write header
            self.file.write('VariableName, Time, Value, Unit\n')

        else:
            self.file = open(filename, 'a')

    def __call__(self, values, variableprefix=''):
        for v in values:
            self.file.write('"{pf}{v.name}", {time}, {v.value:0.6g}, "{v.unit}"\n'
                            .format(v=v, time=v.time.strftime('%Y-%m-%d %H:%M:%S'), pf=variableprefix))
        self.file.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

