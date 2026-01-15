from contextlib import contextmanager

from .exceptions import TrailerError, TrailerWarning, TrailerInfo, TrailerLog
from pathlib import Path
import yaml
import time
from orderedattrdict.yamlutils import AttrDict, AttrDictYAMLLoader



def as_stream(stream_or_path, mode='r'):
    """
    Makes a stream from the given stream, filename or Path
    :param stream_or_path:
    :param mode: the file open mode r|w
    :return: an open stream
    """
    if isinstance(stream_or_path, Path):
        return stream_or_path.open(mode=mode, encoding='utf-8')

    elif isinstance(stream_or_path, str):
        return open(stream_or_path, mode=mode, encoding='utf-8')
    else:
        return stream_or_path

@contextmanager
def stream_scope(stream_or_path, mode='r'):
    stream = as_stream(stream_or_path, mode=mode)
    yield stream
    if hasattr(stream, 'close'):
        stream.close()


def from_yaml(stream_or_path):
    """
    Loads yaml from a stream, path or filename as an attrdict
    :param stream_or_path: A stream, Path or filename(str)
    :return: attrdict.AttrDict
    """
    with stream_scope(stream_or_path) as stream:
        return yaml.load(stream, AttrDictYAMLLoader)

def to_yaml(data, stream_or_path=None):
    """
    Converts data to yaml.
    :param data:
    :param stream_or_path: A stream, path or filename or None to return a string
    :return:
    """
    with stream_scope(stream_or_path, mode='w') as stream:
        return yaml.dump(data, stream, default_flow_style=False)

def on_trailer():
    """
    Returns true if this program runs in the trailer with access to the devices
    :return: bool
    """
    p = Path('/etc/hostname')
    return p.exists() and p.read_text().strip() == 'fb09-trailer'

if on_trailer():
    home = Path('/home/trailer/trailer')
else:
    home = Path(__file__ + '/../..').resolve()

preferences_dir = home / 'preferences'


def get_config(filename: str = None, dir: Path = home / 'preferences') -> AttrDict:
    """
    Loads a yaml configuration file as an object structure
    :param filename: filename in the directory
    :param dir: pathlib.Path pointing to the directory of the config file, default=preferences
    :return: ordereddict.AttrDict with the data from the file
    """
    if not filename:
        if on_trailer():
            filename = 'sampler.config.yaml'
        else:
            filename = 'fakesampler.config.yaml'

    fn = dir / filename
    data = from_yaml(fn)
    return data

class CodeTimer:
    """
    Helper class to detect performance bottlenecks
    
    Usage:
    ct = CodeTimer()
    time.sleep(1.0) # Do heavy stuff
    ct('Stage1')
    time.sleep(0.5) # Do heavy stuff
    ct('Stage2')
    print(ct)
    
    """
    def __init__(self):
        self.start = time.time()
        self.last_t = time.time()
        self.data = []
        self.longest_msg = 0

    def __call__(self, msg):
        t = time.time()
        self.data.append((msg, t - self.last_t))
        self.longest_msg=max(self.longest_msg, len(msg))
        self.last_t = t
        return self

    def __repr__(self):
        return 'CodeTimer, {n} Entries since {t:0.3f}s'.format(n=len(self.data), t=time.time()-self.start)

    def __str__(self):
        return '\n'.join(' - {msg} : {t:0.3f}s'
                         .format(msg=msg.ljust(self.longest_msg), t=t)
                          for msg, t in self.data
                         )



class address:
    alphaIO = '/dev/trailerAlphaIO'
    alphaValves = '/dev/trailerAlphaValves'
    ysi600r = '/dev/trailerYSI'
    robot = '/dev/trailerRobot'
    sdi12 = '/dev/ttyUSB0'
    colorcontrol = 'colorcontrol'
    tribox = 'tribox'
    picarro = 'picarro:51020'
    cwspicarro = 'picarro:51211'
    wago = 'wago'
    maja = '/dev/ttyS0'
    logger = 'localhost:51213'

    @classmethod
    def get(cls, name):
        if '.' in name:
            name = name.split('.')[-1]
        return getattr(cls, name)
