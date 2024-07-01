'''
Created on 17.06.2015

@author: kraft-p
'''
import sqlalchemy as sql
import sqlalchemy.orm as orm
from sqlalchemy.ext.declarative import declarative_base
import json
from contextlib import contextmanager
from trailer import home
def make_engine(filename='data.sqlite'):
    engine = sql.create_engine('sqlite:///{}/{}'.format(home.as_posix(), filename), echo=False)
    with engine.connect() as connection:
        connection.execute(sql.text('PRAGMA journal_mode=WAL;'))
        connection.execute(sql.text('PRAGMA synchronous=1;'))
    return engine

engine = make_engine()


# The WAL journal mode is better suited for medium concurrency and
# will hopefully lead to less database is locked operational Errors
# Sources:
# https://www.sqlite.org/howtocorrupt.html
# https://sqlite.org/wal.html
#

Session = orm.sessionmaker(bind=engine)




@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


class Base:
    """Hooks into SQLAlchemy's magic to make :meth:`__repr__`s."""
    def __repr__(self):
        def reprs():
            for col in self.__table__.c:
                try:
                    yield col.name, str(getattr(self, col.name))
                except:
                    pass

        def formats(seq):
            for key, value in seq:
                yield '%s=%s' % (key, value)

        args = '(%s)' % ', '.join(formats(reprs()))
        classy = type(self).__name__
        return "<%s%s>" % (classy, args)

    def session(self):
        return Session.object_session(self)

    @classmethod
    def query(cls, session):
        return session.query(cls)

    @classmethod
    def get(cls, session, objid):
        return session.query(cls).get(objid)


Base = declarative_base(cls=Base)
metadata = Base.metadata


def primarykey():
    return sql.Column(sql.Integer, primary_key=True)


def stringcol(length=None):
    return sql.Column(sql.String(length))

def intcol():
    return sql.Column(sql.Integer)

def floatcol():
    return sql.Column(sql.Float)


def jsonhandler(obj):
    if hasattr(obj, '__jdict__'):
        return obj.__jdict__()
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat() + 'Z'
    else:
        return obj


def as_json(obj, indent=None):
    return json.dumps(obj, sort_keys=True, indent=indent, default=jsonhandler)
