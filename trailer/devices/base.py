'''
Created on 17.03.2016

@author: kraft-p
'''

import asyncio
import time
import traceback
from orderedattrdict import AttrDict
from trailer import TrailerError, TrailerInfo, TrailerWarning, TrailerLog, get_config, db

debug = False


class DeviceWarning(TrailerWarning):

    def __init__(self, msg, device):
        super().__init__(msg)
        self.device = device
        self.owner = repr(device)


class DeviceError(TrailerError):

    def __init__(self, msg, device):
        super().__init__(msg)
        self.device = device
        self.owner = repr(device)


class DeviceResend(TrailerWarning):

    def __init__(self, msg, device):
        super().__init__(self, msg)
        self.device = device
        self.owner = repr(device)


class DeviceNotActive(TrailerError):

    def __init__(self, device):
        super().__init__(self, '{} not active'.format(device))
        self.device = device
        self.owner = repr(device)


class DeviceMessage(TrailerLog):

    def __init__(self, msg, device):
        super().__init__(msg)
        self.device = device
        self.owner = repr(device)



class ProgressEvent(asyncio.Event):
    """
    An asyncio.Event with a name and a callback to check its progress
    """
    def __init__(self,progresscallback=None,name=None):
        """
        progresscallback: A callback (no args) to get the progress. Should be in 0..1
        """
        super().__init__()
        self.name = name
        self.progresscallback = progresscallback or (lambda : 0.0)
    
    def progress(self):
        return self.progresscallback()
    
    def __str__(self):
        name = self.name or 'event'
        if self.is_set():
            return '{}: done'.format(name)
        else:
            return '{}: {:0.1%}'.format(name,self.progress())

class TimedEvent(ProgressEvent):
    """
    An asyncio.Event with an expected duration. 
    Progress is calculated from the duration
    """
    def __init__(self, until, name=None):
        """
        Until is a timestamp in seconds of the expected ready time
        """
        super().__init__(None,name)
        self.starttime = time.time()
        self.until = until if until>self.starttime-3600*24 else self.starttime + until         

    def start(self, until):
        self.clear()
        self.starttime = time.time()
        self.until = until if until>self.starttime-3600*24 else self.starttime + until         
        
    def progress(self):
        if self.until > self.starttime:
            return min((time.time() - self.starttime) / (self.until - self.starttime), 1.0)
        else:
            return 0.0



class Device(object):
    """
    Base class for all kind of devices in the trailer
    Any device needs to implement the following fields:
     - data: a dictionary holding the data of the instrument.
     - ready: Optional, a asyncio.Event to be set by readstatus
                 when the device finishes a task
     - refreshrate: Time span to wait for readstatus tasks
    
    """
    def __init__(self):
        self.data = AttrDict()
        self.actions = AttrDict()
        self.debug = False
        self.is_ready = ProgressEvent(name=str(self) + ' is ready')
        self.refreshrate = 0.0
        self.active = True
        self.readtime = 0.0
        self.timeout_counter = 0
    def __repr__(self):
        return 'devices.' + self.name

    def __getattr__(self, attr):
        if not hasattr(self, 'data'):
            raise AttributeError(
                '{} has no data to retrieve values from'.format(type(self)))
        if attr in self.data:
            return self.data[attr]
        else:
            raise AttributeError('{} does not provide {}'.format(self, attr))

    def __bool__(self):
        return bool(self.active)

    def time_to_read(self)->bool:
        """
        Returns true if it is time to read the device
        :return: bool
        """
        return (self.active and
                time.time()-self.readtime >= self.refreshrate)

    async def readstatus(self):
        """
        Reads the device and sets the data dict.
        """
        raise NotImplementedError(
            '{} has no readstatus function'.format(type(self)))

    def adddevice(self, name, dev):
        if name in self.data:
            raise AttributeError('Cannot add {} to {}, name exists'.format(name,self))
        else:
            self.data[name] = dev

    def apply_config(self, conf):
        for attr, value in conf.items():
            if hasattr(self, attr):
                setattr(self, attr, value)

    async def handle_conf_event(self, event, conf):
        if debug:
            print('{} handles {}->{}()'.format(self, event, conf.get(event, 'null')))
        
        if event in conf:

            if hasattr(self, conf[event]):
                on_create = getattr(self, conf[event])
                if asyncio.iscoroutinefunction(on_create):
                    if debug:
                        print('{} -> await {!r}.{}()'.format(event, self, conf[event]))
                    await on_create()
                elif callable(on_create):
                    if debug:
                        print('{} -> {!r}.{}()'.format(event, self, conf[event]))
                    on_create()
                else:
                    raise DeviceWarning('{}: {} is not callable'.format(event, conf.get(event)), self)
            else:
                raise DeviceWarning('{} is handler for {}, but not a method of {!r}'.format(conf[event], event, self))


class Devices(AttrDict):
    """
    The Devices class is a dict like object holding the devices with their name
    Attribute style access to the devices is possible too: eg. devices.device1
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return ('Devices({})'
                .format(','.join('%s=%s' % it
                                 for it in self.items())
                        )
                )

    

    def __str__(self):
        return ('Devices:\n    ' + '\n    '
                .join('%s=%s' % it
                      for it in self.items()
                      )
                )
    
    
    def set_debug(self, value:bool=True):
        for d in self.values():
            if hasattr(d, 'debug'):
                d.debug = value
        global debug
        debug = value
        
    def is_debug(self):
        return debug
        
    
    async def handle_conf_event(self, event, conf=None):
        """
        Handles a global device event for all member devices of self
        :param event: the name of the event, eg. on_setup_complete
        :param conf: The global configuration, output of get_conf
        :return:
        """
        conf = conf or get_config()

        if debug:
            print('Devices.handle_conf_event("{}")'.format(event))
        try:
            tasks = [asyncio.ensure_future(d.handle_conf_event(event, conf.devices[n]))
                     for n, d in self.items() if n in conf.devices]
            for t in asyncio.as_completed(tasks, timeout=1):
                await t
        except:
            if debug:
                print('ERROR at', event)
                traceback.print_exc()
            else:
                raise

    async def readstatus(self):
        if debug:
            print('Read status from:', ', '.join(self))
            
        await asyncio.gather(*[d.readstatus()
                               for d in self.values()])
        data = AttrDict()
        for n, d in self.items():
            data[n] = d.data
        return data



    def devicedata(self):
        """
        Returns a dict of dicts with the data dict of each device
        """
        res = AttrDict()
        for k, v in self.items():
            if type(v) is type(self):
                res[k] = v.devicedata()
            else:
                if type(v.data) is dict:
                    db.log(DeviceError(k + ' has dict as data, not AttrDict', v))
                res[k] = v.data if hasattr(v, 'data') else {}
                res[k]['active'] = v.active
        return res



