#!/usr/bin/env python3
import sys
from datetime import datetime, timedelta
from trailer.logger import db
from numpy import polyfit

sources = {'soc': (9, 35, 95), 'fuel' : (25, 20, 85)}

class FullPower(Exception):
    def __init__(self):
        super().__init__('No projection, was fully charged in the last hour')

def project(source_id, lowerlimit, upperlimit):
    with db.session_scope() as session:
        values = (session.query(db.LoggerValue)
                  .filter_by(source_id=source_id)
                  .order_by(db.LoggerValue.time.desc())
                  .limit(12)).all()
        # Full load in query, no projections possible
        if any(v.value > upperlimit for v in values):
            raise FullPower()
        else:
            t = []
            v = []
            now = datetime.utcnow().timestamp()
            for val in values:
                t.append(val.time.timestamp()-now)
                v.append(val.value)
            # make lin regr in form y=a*t + b
            a, b = polyfit(t, v, 1)
            return (lowerlimit-b)/a


if __name__ == '__main__':
    if len(sys.argv) > 1:
        param = sys.argv[1]
    else:
        param = 'soc'
    try:
        params = sources[param]
    except (KeyError, IndexError):
        sys.stderr('No parameters for "{}" specified.'.format(param))
        sys.stderr('Usage: tools/generator_projection [{}]'.format('|'.join(sources)))
    try:
        res = project(*params)
        td = timedelta(seconds=res)
        print('{} to go while {} > {} '.format(td, param, params[1]))
    except FullPower as e:
        print(e)
