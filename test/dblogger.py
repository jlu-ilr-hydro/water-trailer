#!/usr/bin/env python3
import sys
sys.path.append('.')
import pandas as pd
from trailer.logger import db
from trailer.db.engine import engine, metadata
from trailer.logger.bus import Value
import datetime

db.debug = True

metadata.create_all(engine)

def str2time(s):

    return datetime.datetime.strptime(s.strip(), '%Y-%m-%d %H:%M:%S')

data = pd.read_csv('log-2017-03-10.csv')
timepoints = sorted(set(data.Time))

wait = True

for t in timepoints:
    ledata = data[data.Time == t]
    print('{}: {} values'.format(t, len(ledata)))
    values = [Value(name=vn, time=str2time(t),
                    value=v, unit=u)
              for vn, v, u in
              zip(ledata.VariableName, ledata.Value, ledata.Unit)]

    newvalues = db.submit(values)
    if newvalues:
        print('      added sources:' + ', '.join(newvalues))
    if wait:
        wait = input().strip()
