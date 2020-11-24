'''
Created on 16.06.2015

@author: kraft-p
'''
from orderedattrdict import AttrDict

from .engine import Base
from .engine import primarykey, stringcol, floatcol, session_scope, intcol
from .engine import sql, orm

from trailer.exceptions import TrailerError, TrailerWarning
import datetime
import calendar


class DbError(TrailerError):
    pass


class DbWarning(TrailerWarning):
    pass


class ValueType(Base):
    """
    ValueTypes describe what is measured and holds the unit of the measurement
    """
    __tablename__ = 'valuetype'
    id = primarykey()
    name = sql.Column(sql.String, unique=True)
    name_html = stringcol()
    unit = stringcol()
    unit_html = stringcol()
    comment = stringcol()

    __iddict = {}

    @classmethod
    def all(cls):
        with session_scope() as session:
            res = session.query(cls).all()
            session.expunge_all()
        return res

    @classmethod
    def get_id(cls, name):
        if not cls.__iddict:
            alltypes = cls.all()
            cls.__iddict = dict((vt.name, vt.id) for vt in alltypes)
        return cls.__iddict.get(name)

    @classmethod
    def create(cls, name, session):
        if cls.get_id(name):
            raise DbError('ValueType "{}" exists already'.format(name))
        res = cls(name=name)
        session.add(res)
        session.flush()
        cls.__iddict[name] = res.id
        return res

    def to_json(self):
        return AttrDict(id=self.id, name=self.name, name_html=self.name_html,
                        unit=self.unit, unit_html=self.unit_html,
                        comment=self.comment)

    @classmethod
    def from_json(cls, session, data):
        res = cls(**data)
        session.add(res)
        return res


class Site(Base):
    """
    Describes the site, where the trailer is installed.

    id: Auto incremented position id
    name: Name of the site
    start: Installation date of the trailer at the site
    end: Deinstallation date of the trailer at the site
    lon: Longitude (WGS84) in decimal degrees
    lat: Latitude (WGS84) in decimal degrees
    comment: Any useful comments concerning the site
    svg: SVG image that shows a site sketch
    """
    __tablename__ = 'site'
    id = primarykey()
    name = stringcol()
    start = sql.Column(sql.DateTime)
    end = sql.Column(sql.DateTime)
    lon = floatcol()
    lat = floatcol()
    comment = stringcol()
    svg = stringcol()


class Source(Base):
    """
    Describes a unique water source. For each new site of the trailer,
    new sources are created.

    id: Auto incrementing id number
    name: Name of the source (Eg. stream 1, piezometer A).
          The name should appear in the site.svg sketch
    flushtime: Time in s how long the source should be flushed
    flushspeed: ml/s from calibration
    samplevolume: Volume to take for each sample from this source in ml
    valveid: The id of the valve connected with this source.
             0 or None means unconnected
    """
    __tablename__ = 'source'
    id = primarykey()
    _site = sql.Column('site', sql.Integer, sql.ForeignKey('site.id'))
    site = orm.relationship('Site')
    name = stringcol()
    flushtime = floatcol()
    flushspeed = floatcol()
    samplevolume = floatcol()
    valveid = sql.Column(sql.Integer)
    comment = stringcol()
    dataset = intcol()

    def get_last_sample(self):
        """
        Returns the last sample taken from this source.
        Returns None if no sample has been taken
        """
        sample = (self.session().query(Sample)
                  .filter_by(_source=self.id)
                  .order_by(sql.desc(Sample.time))
                  .first()
                  )
        return sample

    def makesample(self):
        return Sample.create(self.session(), self.id)

    def to_json(self):
        return AttrDict(id=self.id, _site=self._site, name=self.name,
                        flushtime=self.flushtime, flushspeed=self.flushspeed,
                        samplevolume=self.samplevolume, valveid=self.valveid,
                        comment=self.comment)

    @classmethod
    def from_json(cls, session, data):
        res = cls(**data)
        session.add(res)
        return res


class Sample(Base):
    """
    A Sample is the description for one water sample pumped to the reservoir.
    The measurements of the sample are stored as Values.

    Addtional properties:
    :id: autoincremented identification number
    :source: The source of the sample (eg. stream 1, Piezometer A etc.)
    :time: The time of the sampling
    :ok: Boolean if everything went ok with the sampling
    :storageid: sample number in the sampling storage. NULL means not stored
        Numbering scheme:
        i // 10000: Fill number, is incremented each time the storage racks are
                    refilled with empty bottles
        (i % 10000)// 1000: Rack number, as labeled on the rack in the fridge
        i % 1000: Bottle number. Bottle 1 is the upper left,
                  2 the right neighbor of 1
    """
    __tablename__ = 'sample'
    id = primarykey()
    _source = sql.Column('source', sql.Integer,
                         sql.ForeignKey('source.id'),
                         nullable=False)
    source = orm.relationship('Source')
    time = sql.Column(sql.DateTime, nullable=False)
    ok = sql.Column(sql.Boolean, nullable=False, default=False)
    storageid = sql.Column(sql.Integer)
    comment = stringcol()

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self._source = kwargs.get('_source')
        self.source = kwargs.get('source')
        self.time = kwargs.get('time', datetime.datetime.utcnow())
        self.ok = kwargs.get('ok', False)
        self.storageid = kwargs.get('storageid')
        self.comment = kwargs.get('comment')

    def __str__(self):
        return 'Sample from {} at {:%Y-%m-%d %H:%M:%S}'.format(
                    self.source.name, self.time)

    def __repr__(self):
        return "Sample(id={},_source={},time={},comment={})".format(
                self.id, self._source, self.time, self.comment)

    def __getitem__(self, valuetypename):
        vtdict = self.valuedict()
        if valuetypename in vtdict:
            return vtdict[valuetypename]
        else:
            raise KeyError('{} not measured for {}'
                           .format(valuetypename, self))

    @classmethod
    def create(cls, session, sourceid, time=None, comment=None):
        """
        Creates a new sample for the source with ID sourceid
        """
        source = session.query(Source).get(sourceid)
        if source is None:
            raise DbError('No source with id={} exists'.format(sourceid))
        if time is None:
            time = datetime.datetime.utcnow()
        sample = cls(source=source, time=time, comment=comment)
        session.add(sample)
        return sample
    
    def gettimestamp(self):
        return calendar.timegm(self.time.timetuple())

    def addcomment(self, msg):
        """
        Adds more comment to the sample. Comments are seperated by |
        """
        if not self.comment:
            self.comment = msg
        elif msg not in self.comment:
            self.comment += '|' + msg

    def addvalues(self, data: AttrDict=None, **kwargs):
        """
        Adds values from the keywords to the sample.
        If a ValueType with the name of the keyword
        does not exist, a new valuetype is created.

        :returns: A list of keywords that were not registered
                  as valuetypes before
        """
        if data:
            data.update(kwargs)
        else:
            data = kwargs

        newvaluewarnings = []
        for name, value in data.items():
            vtid = ValueType.get_id(name)
            # Check if valuetype exists already
            if vtid is None:
                # Name not present in database
                vtid = ValueType.create(name, self.session()).id
                newvaluewarnings.append(name)
            Value.create(self.session(), vtid, self.id, value)
        return newvaluewarnings

    def valuedict(self):
        return AttrDict((v.valuetype.name, v.value) for v in self.values)
    
    def to_json(self, withsource=False):
        """
        Creates a json compatible dictionary for
        sending a sample over the network
        """
        d = AttrDict(id=self.id, _source=self._source,
                     time=self.time, ok=self.ok,
                     storageid=self.storageid,
                     comment=self.comment,
                     values=self.valuedict(),
                     name=str(self))
        if withsource:
            d['source'] = self.source.to_json()
        return d

    @classmethod
    def from_json(cls, session, data):
        values = data.pop('values')
        try:
            data['time'] = datetime.datetime.strptime(data['time'],
                                                      '%Y-%m-%dT%H:%M:%S.%f')
        except:
            pass
        res = cls(**data)
        session.add(res)
        res.addvalues(**values)
        return res


def addvalues(sampleid, session, **kwargs):
    sample = session.query(Sample).get(sampleid)
    if not sample:
        raise ValueError('Sample with id={} does not exist'.format(sampleid))
    sample.addvalues(**kwargs)
    return sample


class Value(Base):
    """
    A Value is the single measurement of a sample
    """
    __tablename__ = 'value'
    sample_id = sql.Column('sample_id', sql.Integer,
                           sql.ForeignKey('sample.id'),
                           primary_key=True)
    valuetype_id = sql.Column('valuetype_id', sql.Integer,
                              sql.ForeignKey('valuetype.id'),
                              primary_key=True)
    sample = orm.relationship('Sample', lazy='select',
                              backref=orm.backref('values'))
    valuetype = orm.relationship('ValueType', lazy='select')
    value = sql.Column(sql.Float, nullable=False)

    def __repr__(self):
        return '%g%s %s in %s' % (self.value, self.valuetype.unit,
                                  self.valuetype.name, self.sample)

    def __html__(self):
        return '%g%s %s in %s' % (self.value, self.valuetype.unit_html,
                                  self.valuetype.name_html, self.sample)

    @classmethod
    def create(cls, session, valuetype_id, sample_id, value):
        value = float(value)
        res = cls(sample_id=sample_id, valuetype_id=valuetype_id, value=value)
        session.add(res)
        return res

if __name__ == '__main__':
    from .engine import engine, Session, as_json

    Base.metadata.create_all(engine)  # @UndefinedVariable
    source = Source(name='test', valveid=11)
    session = Session()
    session.add(source)
    session.flush()
    sample = Sample.create(session, 1)
    sample.addcomment('bla')
    session.flush()
    sample.addvalues(a=1.2, b=3, c=0.4)
    session.commit()
    jsn = as_json(sample.to_json())
    print(jsn)
    import json
    data2 = json.loads(jsn)
    data2['id'] = 2
    s2 = Sample.from_json(session, data2)
