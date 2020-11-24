from orderedattrdict import AttrDict

from ..db.engine import Base, sql, orm, session_scope
from ..db.engine import stringcol, intcol
import calendar

debug = False


class LoggerSource(Base):
    """
    Describes the type of the logger value
    """
    __tablename__ = 'loggersource'

    id = sql.Column(sql.Integer, primary_key=True, autoincrement=True)
    name = sql.Column(sql.String, nullable=False)
    name_html = stringcol()
    unit = stringcol()
    unit_html = stringcol()
    dataset_id = intcol()
    comment = stringcol()

    def __repr__(self):
        return 'LoggerSource(id={},name={}->ds:{})'.format(self.id, self.name, self.dataset_id)

    def __str__(self):
        return '{} in {}'.format(self.name, self.unit)

    def __html__(self):
        return '{} in {}'.format(self.name_html or self.name,
                                 self.unit_html or self.unit)

    def to_json(self):
        return AttrDict(id=self.id, name=self.name, name_html=self.name_html,
                        unit=self.unit, unit_html=self.unit_html,
                        comment=self.comment)


class LoggerValue(Base):

    __tablename__ = 'loggervalue'

    time = sql.Column(sql.DateTime, primary_key=True)

    source_id = sql.Column('source_id', sql.Integer,
                           sql.ForeignKey('loggersource.id'),
                           primary_key=True)

    source = orm.relationship('LoggerSource')

    value = sql.Column(sql.Float)

    def __repr__(self):
        return 'LoggerValue(event_id={}, source_id={}, value={:0.6g}'.format(
            self.event_id, self.source_id, self.value)

    def __str__(self):
        return '{name}={value:0.5g}{unit} at {time:%Y-%m-%d %H:%M:%S}'.format(
            name=self.source.name, value=self.value,
            unit=self.source.unit, time=self.event.time)

    def __html__(self):
        return '{name}={value:0.5g}{unit} at {time:%Y-%m-%d %H:%M:%S}'.format(
            name=self.source.name_html or self.source.name,
            value=self.value,
            unit=self.source.source.unit_html or self.source.unit,
            time=self.time)

    def gettimestamp(self):
        return calendar.timegm(self.time.timetuple())


def submit(values):
    """
    Submits a list of trailer.logger.bus.base.Values to the database
    :param values:
    :return:
    """
    with session_scope() as session:
        time = values[0].time
        names = [v.name for v in values]

        # Find logger sources
        q = session.query(LoggerSource).filter(
            LoggerSource.name.in_(names))
        lsdict = {ls.name: ls for ls in q}

        # create missing logger sources
        newvaluewarnings = []
        for v in values:
            if v.name not in lsdict:
                # Name not present in database
                ls = LoggerSource(name=v.name,
                                  unit=v.unit,
                                  dataset_id=v.datasetid)
                session.add(ls)
                lsdict[v.name] = ls
                newvaluewarnings.append(v.name)

        if newvaluewarnings:
            session.commit()

        # Add values
        for v in values:
            session.add(
                LoggerValue(
                    source_id=lsdict[v.name].id,
                    time=time,
                    value=v.value
                )
            )

        return newvaluewarnings

