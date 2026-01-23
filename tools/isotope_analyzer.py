#/usr/bin/env python3
import sys
"""
Gets isotopic data from the database, creates an interpolation for
the standard measurements and gives a tool to calibrate at any time using 
an interpolated standard measurement for the given timestep. This tool
is in development and a first draft of the final shape
"""


import numpy as np

from scipy.interpolate import interp1d
from datetime import datetime, timedelta
from trailer import db

def date2num(dt: datetime):
    """
    Equals date2num from matplotlib
    :param dt: The datetime object to transform
    :return: days from 1.1.0001 until dt as float
    """
    return (dt - datetime(1, 1, 1)) / timedelta(days=1)

def append2dict(dct, k, val):
    """
    Appends values to a dict of lists. Creates a new list if the key is missing
    :param dct: The dict to append to
    :param k: The key to append to
    :param val: The value to append to dct[k]
    :return: None
    """
    dct.setdefault(k, []).append(val)

def get_data(session, valuetype_id,
             start_sample=0, end_sample=10000000,
             source_id=None):
    """
    Helper function to get a list of values from the db
    :param session: an open sqlalchemy session
    :param valuetype_id: The valuetype we are looking for (only the id!), or a sequence of ids
    :param start_sample: A filter for a sample range
    :param end_sample:  A filter for a sample range
    :param source_id: A filter for a certain source
    :return: list of db.Value objects
    """
    try:
        vt0 = valuetype_id[0]
    except TypeError:
        q = (session.query(db.Value)
             .filter_by(valuetype_id=valuetype_id)
             .filter(db.Value.sample_id.between(start_sample, end_sample))
             .order_by(db.Value.sample_id)
             )
        return [v for v in q if source_id is None or v.sample.source.id == source_id]
    else:
        q = (session.query(db.Value)
             .filter(db.Value.valuetype_id.in_(valuetype_id))
             .filter(db.Value.sample_id.between(start_sample, end_sample))
             .order_by(db.Value.sample_id)
             )
        return [v for v in q if source_id is None or v.sample.source.id == source_id]

# TODO: Get timeseries instead of constants, too
# standards with the following values were used from 19.10.2017
real_values = {10: # Valuetype d2H
                   {
                    6: -1.52, # 2H Std1 (source_id of std1)
                    5: -164.60, # 2H Std2 (source_id of std2)
                   },
               11: # Valuetype d18O
                   {
                       6: +3.13, # 18O Std1 (6=source_id of std1)
                       5: -22.43, # 18O Std2 (5=source_id of std2)
                   }
               }

class RealValuePseudoInterpolator:
    def __init__(self, valuetye_id, source_id):
        self.vtid = valuetye_id
        self.sid = source_id
    def __call__(self, dt: datetime):
        return real_values[self.vtid][self.sid]


class Interpolator:
    """
    Holds a fitting interpolator for a standard / isotope combination
    A calibrator needs 4 Interpolators, one for each standard the measured and the real value
    """
    def __init__(self, session, valuetype_id, std_id, start_sample, end_sample):
        """
        Creates a calibration object for isotopes
        :param session: a database session
        :param valuetype_id: 10 (2H) or 11 (18O)
        """
        self.std_id = std_id
        valuetype = str(session.query(db.ValueType).get(valuetype_id))
        if not valuetype:
            raise ValueError('No value type with id {} in database'.format(valuetype_id))
        else:
            self.valuetype = str(valuetype)
        self.valuetype_id = valuetype_id
        self.start_sample = start_sample
        self.end_sample = end_sample
        values = get_data(session, valuetype_id, start_sample, end_sample, std_id)
        if not values:
            raise ValueError('No values of type {} found for source #{} \n' +
                             'between sample #{} and #{}'.format(valuetype, std_id, start_sample, end_sample))
        # Get numeric sample time representation for all standard measurements
        t = np.fromiter((date2num(v.sample.time) for v in values), np.double, count=len(values))
        # Get value for standard measurements (either live CoWS or Lab)
        y = np.fromiter((v.value for v in values), np.double, count=len(values))
        # Determine interpolation order from number of values
        interpolation_order = 1 # min(len(y)-1, 1)
        # Make the interpolation function
        self.__measured = interp1d(x=t, y=y, kind='linear',
                                   bounds_error=False, fill_value='extrapolate')

    def __call__(self, dt: datetime):
        """
        Returns the interpolated value
        :param dt: The datetime to interpolate at
        :return: the interpolated value
        """
        return self.__measured(date2num(dt))

class Calibrator:
    """
    Calibrates an isotopic value using two-point calibration
    """
    def __init__(self, real_interp1, measured_interp1, real_interp2, measured_interp2):
        self.interpolators = real_interp1, measured_interp1, real_interp2, measured_interp2

    def regression(self, dt: datetime):
        """
        Returns the regression parameters for time dt
        :param dt: the datetime for the regression parameters
        :return: a, b, t = offset, slope, date2num timestamp
        """
        # Get timestamp
        t = date2num(dt)
        # Get interpolated values
        r1, o1, r2, o2 = [i(dt) for i in self.interpolators]
        # Calculate slope
        b = (r1 - r2) / (o1 - o2)
        # Calculate offset
        a = r1 - (b * o1)

        return a, b, t

    def __call__(self, dt: datetime, value: float):
        """
        Calibrates the measured value 
        :param dt: 
        :param value: 
        :return: 
        """
        # Get the regression parameters for dt and the timestamp
        a, b, t = self.regression(dt)
        return t, b * value + a


def plot_values(d, title='', unit=''):
    import pylab as plt
    plt.figure()
    for k in d:
        if k.startswith('Real'):
            pass
        elif k.startswith('Rain'):
            plt.plot_date(*(np.array(d[k]).T), 'x', label=k)
        else:
            plt.plot_date(*(np.array(d[k]).T), 'x-', label=k)
    plt.legend()
    plt.title(title)
    plt.ylabel(unit)
    plt.show()

if __name__ == '__main__':
    do_plot = 'plot' in sys.argv
    outfn = sys.argv[1] if len(sys.argv)>1 else 'result.csv'
    d2H = 10
    d18O = 11
    std1_id = 6
    std2_id = 5
    start = 294231
    end = 10000000000
    with db.session_scope() as session:

        d2H_calib = Calibrator(
            RealValuePseudoInterpolator(d2H, std1_id),
            Interpolator(session, d2H, std1_id, start, end),
            RealValuePseudoInterpolator(d2H, std2_id),
            Interpolator(session, d2H, std2_id, start, end),
        )

        d18O_calib = Calibrator(
            RealValuePseudoInterpolator(d18O, std1_id),
            Interpolator(session, d18O, std1_id, start, end),
            RealValuePseudoInterpolator(d18O, std2_id),
            Interpolator(session, d18O, std2_id, start, end),
        )

        d2H_values = {}
        d18O_values = {}
        if not do_plot:
            with open(outfn, 'w') as fout:
                fout.write('source, sample_id, time, d2H, d18O\n')
                for v in get_data(session, [d2H, d18O], start, end):
                    t = v.sample.time
                    print(t)
                    if v.valuetype_id == d2H:
                        _, calib_value = d2H_calib(t, v.value)
                        fout.write('{s}, {id}, {t}, {v:0.8g}'
                                   .format(id=v.sample_id, t=t,
                                           v=calib_value,
                                           s=v.sample.source.name))
                    else:
                        _, calib_value = d18O_calib(t, v.value)
                        fout.write(', {v:0.8g}\n'.format(v=calib_value))

        else: # do plot

            for d, vt, c in zip([d2H_values, d18O_values], [d2H, d18O], [d2H_calib, d18O_calib]):
                for v in get_data(session, vt, start, end):
                    append2dict(d, v.sample.source.comment, c(v.sample.time, v.value))
            d2H_vt = session.query(db.ValueType).get(d2H)
            d18O_vt = session.query(db.ValueType).get(d18O)

            plot_values(d2H_values, d2H_vt.comment, d2H_vt.unit)
            plot_values(d18O_values, d18O_vt.comment, d18O_vt.unit)

