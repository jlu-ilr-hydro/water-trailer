#!/usr/bin/env python3
"""
Plots the sources as dD against d18O with error bars for the
measurement
"""
from itertools import product

import pylab as plt
from attrdictionary import AttrDict
from trailer import db

def get_values():
    with db.session_scope() as session:
        vt = AttrDict()
        data=AttrDict()
        for v, std_mean in product(['d2H', 'd18O'], ['mean', 'std']):
            vt.setdefault(v, AttrDict())
            vt[v][std_mean] = (session.query(db.ValueType)
                                .filter_by(name='{}_{}'.format(v, std_mean))
                                .first())
            print('Load {}_{} from {}'.format(v, std_mean, vt[v][std_mean]))
            data.setdefault(v, AttrDict())
            data[v][std_mean] = (session.query(db.Value)
                                  .filter_by(db.Value.valuetype_id=vt[v][std_mean].id)
                                  .all()
            )
        return data

if __name__ == '__main__':
