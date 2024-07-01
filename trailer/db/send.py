from attrdictionary import AttrDict
import yaml
import gzip
import io
import requests

from .. import TrailerError, TrailerLog, get_config
from .engine import engine, session_scope, sql
from .log import log, LogEntry, time_since_log
from .sample import Sample, Source, Value, ValueType
from ..logger.db import LoggerValue, LoggerSource


class ExportError(TrailerError):
    pass


def get_tables():
    """
    Gets an AttrDict of the sql.table objects from the database. In case of new tables, expand
    :return:
    """
    tables = AttrDict()
    tables.log = LogEntry.__table__
    tables.valuetype = ValueType.__table__
    tables.source = Source.__table__
    tables.sample = Sample.__table__
    tables.value = Value.__table__
    tables.loggersource = LoggerSource.__table__
    tables.loggervalue = LoggerValue.__table__
    return tables


def get_last_export_id():
    """
    Finds the last export log and reads the last exported id in there
    :return:
    """
    last_export_id = AttrDict()
    # Get last export log entry using the sqalchemy orm interface
    with session_scope() as session:
        last_export_log = session.query(LogEntry).filter_by(owner='db.send').order_by(LogEntry.id.desc()).first()

        if last_export_log:
            last_export_id.update(yaml.load(last_export_log.msg))
    return last_export_id


def get_id_col(t)->sql.Column:
    """
    Returns the id column of a table
    :param t:
    :return:
    """
    for pc in ('id', 'time', 'sample_id'):
        if pc in t.c:
            return t.c[pc]
    else:
        raise ExportError('No column id or time available in table ' + t.name)


def get_current_export_id():
    """
    Gets the current id's present in the database
    :return:
    """
    tables = get_tables()
    res = AttrDict()
    for tn, t in tables.items():
        id_col = get_id_col(t)
        stmt = sql.select([sql.func.max(id_col)])
        with engine.connect() as conn:
            res[tn] = conn.scalar(stmt)
    return res

def log_update(last_export_id):
    """
    Writes a log which id's have been exported
    :param last_export_id:
    :return:
    """
    msg = yaml.dump(last_export_id)
    log(TrailerLog(msg, owner='db.send'))


def collect_update(last_export_id=None, verbose=False, last_sample=None):
    """
    Get all new rows (as given from last_export_id) from the database and packs them in gzip strings.
    :param last_export_id: A mapping containing the last exported id for the tables. If None, this item will
                            be retrieved from the log
    :param verbose:
    :param last_sample: Optional: the id of the last sample to export. By specifying last_sample the export of
            unfinished samples are prevented
    :return: an AttrDict of tablenames and gzip representation of the data from the respective tables.
    """
    # shortcuts for the tables
    tables = get_tables()

    if last_export_id is None:
        last_export_id = get_last_export_id()
    if verbose:
        print(last_export_id)
    # we just want to get the data as big lists in memory, so we use the sql interface of sqalchemy
    out = io.BytesIO()
    linecount = 0
    with gzip.GzipFile(fileobj=out, mode='wb') as gz_out:
        for tn, t in tables.items():
            select_column = get_id_col(t)
            if verbose:
                print('select from {} where {}>{};'.format(tn, select_column, last_export_id[tn]))
            # Get all new values
            s = t.select().where(select_column > last_export_id.get(tn, -1))
            if last_sample and tn in ['sample', 'value']:
                s = s.where(select_column <= last_sample)
            # Load the data into memory
            out_list = []
            with engine.connect() as conn:
                for row in conn.execute(s):
                    linecount += 1
                    out_list.append(list(row))
                    last_export_id[tn] = row[select_column.name]
                    if not linecount % 1000:
                        print(linecount,' lines exported')
            yaml.dump({tn: out_list}, gz_out, encoding='utf-8')
            if verbose:
                print(tn, 'exported', linecount, 'lines')

    return out.getvalue(), last_export_id, linecount


def send_update(last_sample=None, verbose=False):
    """
    Posts an db update to the url given in conf.mirror_db.url. Does not send (return directly)
    if the timegap from conf has not passed
    :param last_sample: Optional: the id of the last sample to export. By specifying last_sample the export of
            unfinished samples are prevented
    :param verbose: Prints messages to the screen about the export
    :return:
    """
    conf = get_config()
    if not conf.get('mirror_db'):
        return
    # check if it is enough time since last update:
    if not time_since_log('db.send') >= conf.mirror_db.get('timegap', 0):
        return
    if verbose:
        print('export to ', conf.mirror_db.url)
    # Collect the update data
    data, last_export_id, line_count = collect_update(verbose=verbose)
    # post the update data to the mirror_db
    r = requests.post(url=conf.mirror_db.url,
                      data=data)
    # check if mirror responses with the correct number of lines
    if r.text.strip() == str(line_count):
        # if ok, log the successful update
        log_update(last_export_id)
    elif verbose:
        print('Update was not succesful')
        print(r.text)


def receive_update(datastream, verbose=False):
    """
    Receives the current daabase status to updates its own. This is called on the mirror db
    :param datastream: A mapping of tablenames with gzipped yaml representation of rows, as produced by send
    :param verbose:
    :return: Number of imported lines
    """
    tables = get_tables()
    linecount = 0
    with gzip.GzipFile(fileobj=datastream) as gz_in:
        data = yaml.load(gz_in)
    for tn, ls_data in data.items():
        if tn not in tables:
            print(tn, 'not found')
            continue
        t = tables[tn]
        if ls_data:
            for i in range(0, len(ls_data), 1000):
                ins_data = [dict([(c.name, v)
                                  for c, v in zip(t.c, line)])
                            for line in ls_data[i:i+1000]]
                with engine.connect() as conn:
                    conn.execute(t.insert(), ins_data)
                linecount += len(ins_data)
                if verbose:
                    print(linecount)
        if verbose:
            print('{} rows imported into {}'.format(len(ls_data), tn))
    return linecount







