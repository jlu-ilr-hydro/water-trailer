'''
Created on 17.06.2015

@author: kraft-p
'''
from orderedattrdict import AttrDict

from .engine import Base
from .engine import primarykey, stringcol, session_scope
from .engine import sql

import datetime
import traceback

class LogEntry(Base):
    __tablename__ = 'log'
    id = primarykey()
    msg = stringcol()
    time = sql.Column(sql.DateTime)
    owner = stringcol()
    level = sql.Column(sql.Integer, index=True)

    def to_json(self):
        return AttrDict(id=self.id, msg=self.msg,
                        time=self.time, owner=self.owner, level=self.level)

    @classmethod
    def from_json(cls, session, data):
        res = cls(**data)
        session.add(res)
        return res


debug = True


def log(msg, session=None):
    if msg is None:
        return
    t = datetime.datetime.utcnow()
    entry = LogEntry(msg=msg.message, time=t, owner=msg.owner, level=msg.level)
    if session:
        session.add(entry)
        session.flush()
        id = entry.id
    else:
        with session_scope() as session:
            session.add(entry)
            try:
                session.flush()
            except Exception as e:
                print('session.flush() in log.py:50 failed')
                traceback.print_exc()
                raise
            id = entry.id
    if debug:
        print('{} {} {} {}'.format(msg.level, t, msg.message, msg.owner))
    return 'log:{}'.format(id)


def readlog(session, level=100, count=1, owner=None):
    """
    Reads entries from the logbook
    :param session: a db.session to query
    :param level: Level of logs, default all levels
    :param count: Number of logs to return
    :param owner: Owner of log entry, if left out all entries are given
    :return: List of AttrDict's of LogEntries
    """
    logs = session.query(LogEntry).filter(LogEntry.level <= level)
    if owner:
        logs = logs.filter_by(owner=owner)
    logs = logs.order_by(LogEntry.time.desc())
    logs = logs.limit(count)

    return [log.to_json() for log in logs]


def last_log(owner):
    """
    Returns the last logentry from the given owner. If you have a session already
    use readlog(session, owner=owner) instead
    :param owner: Owner of the log
    :return: AttrDict of LogEntry
    """
    with session_scope() as session:
        logs = readlog(session, owner=owner)
        if logs:
            return logs[0]
        else:
            return

def time_since_log(owner):
    now = datetime.datetime.utcnow()
    ll = last_log(owner)
    if ll:
        return (now - ll.time).total_seconds()
    else:
        return (now - datetime.datetime(2017, 1, 1)).total_seconds()