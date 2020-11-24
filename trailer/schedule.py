"""
Created on 18.06.2015

@author: kraft-p
"""
from orderedattrdict import AttrDict
from datetime import datetime, timedelta
import time
from itertools import cycle

from . import to_yaml, from_yaml, preferences_dir, Path
from .devices import Devices
from .db.log import log
from . import TrailerInfo


def path2name(path: Path):
    return path.name.replace('.schedule.yaml', '')


def name2path(name) -> Path:
    return preferences_dir / '{}.schedule.yaml'.format(name)

def td(seconds):
    return timedelta(seconds=seconds)

class Event(object):

    def __init__(self, tag, condition, blocktime=0.0):
        """
        tag - a source id or any other information that is fired when the event is due
        condition - a piece of Python code that evaluates to True. To fire the event
                    when the value "abc" of device "mydev" is 5, then the condition is 
                    mydev.abc == 5
        blocktime - time in seconds to block the event to prevent frequent firing
        """
        if '.' not in condition:
            raise ValueError('The condition needs to be in the format ' +
                             'device.value == 5, where you can use any ' +
                             'boolean operator')
        self.condition = condition
        self.blocktime = float(blocktime)
        self.tag = tag
        self.fired = 0.0

    def __call__(self, devices: Devices):
        """
        Checks the condition. If it is true, return tag, else None
        """
        try:
            happens = eval(self.condition, {}, devices)
        except Exception:
            happens = False
        if time.time() - self.blocktime >= self.fired and happens:

            self.fired = time.time()
            return self.tag
        else:
            return None

    def __jdict__(self):
        return AttrDict(condition=str(self.condition),
                        tag=self.tag,
                        blocktime=self.blocktime)

    def __repr__(self):
        return ('if {} then {} after {:0.1f s}'
                .format(self.condition, self.tag, self.blocktime))


class Schedule(object):
    """
    Scheduler of sources
    
    The schedule consists of 2 queues
     - urgentsources: Sources that are scheduled by an event or manually
     - sourcequeue: Normal queue of sources with wait time (time_per_source)
    
    Events that schedule sources in the urgentsources queue are 
    stored in the events list.
    """

    def __init__(self, time_per_source=600):
        self.sourcequeue = []
        self.sourcepointer = -1
        self.time_per_source = time_per_source
        self.urgentsources = []
        self.currentsource = None
        self.starttime = datetime.utcnow() - td(time_per_source * 2)
        self.events = []
        self.name = None
        
    def nextsample(self):
        """
        Creates a new sample in the database session
        using the next source
        """
        if self.urgentsources:
            self.currentsource = self.urgentsources.pop(0)
        elif self.sourcequeue:
            self.sourcepointer = (self.sourcepointer + 1) % len(self.sourcequeue)
            self.currentsource = self.sourcequeue[self.sourcepointer]
        else:
            return None
        self.starttime = datetime.utcnow()
        self.save()
        return self.currentsource, datetime.utcnow()

    def skip_next(self):
        self.sourcepointer = (self.sourcepointer + 1) % len(self.sourcequeue)
        self.save()

    def append(self, sourceid):
        """
        Appends a sourceid to the normal schedule
        """
        self.sourcequeue.append(sourceid)

    def extend(self, sourceid_sequence):
        """
        Extends the schedule with a sequence of sourceids
        """
        self.sourcequeue.extend(sourceid_sequence)

    def addevent(self, condition, sourceid):
        """
        Adds an event source. Will be scheduled if "condition" is fullfilled
        """
        self.events.append(Event(sourceid, condition))

    def index(self, sourceid):
        """
        Returns the position of the source id

        """
        for i, s in enumerate(self.sourcequeue):
            if s == sourceid:
                if i <= self.sourcepointer:
                    return i + len(self.sourcequeue) - self.sourcepointer
                else:
                    return i - self.sourcepointer
        raise IndexError('Source #{} not in schedule')

    def peek(self):
        """
        Returns the source id on the next position
        """
        if self.urgentsources:
            return self.urgentsources[0]
        elif self.sourcequeue:
            return self.sourcequeue[(self.sourcepointer + 1) % len(self.sourcequeue)]
        else:
            return None

    def future(self, n=5):
        """
        Returns a list of the next n sources to sample
        """
        now = datetime.utcnow()
        # Urgent sources first, all due now
        res = [(s, now) for s in self.urgentsources]

        # Get the actual queue, starting at the pointer
        actual_queue = self.sourcequeue[self.sourcepointer + 1:][:(n - len(res))]
        # Then queue sources, due time calculated from start time
        res += [(s, self.starttime + td((i + 1) * self.time_per_source))
                for i, s in enumerate(actual_queue)]
        offset = len(actual_queue) + 1
        # Fill the queue up with repetions of the sourcequeue until we have n values
        for i, s in enumerate(cycle(self.sourcequeue)):
            if len(res) < n:
                res.append((s, self.starttime + td((i + offset) * self.time_per_source)))
            else:
                break
        return res

    def due(self, sourceid=None):
        """
        Returns the estimated time until this source will be measured
        """
        # dist is the numbers of sources coming before sourceid
        if sourceid is None:
            dist = 0  # using the actual source
        elif sourceid in self.urgentsources:
            # sourceid is a urgent source
            dist = self.urgentsources.index(sourceid)
        elif sourceid in self.sourcequeue:
            # source id is in the source queue
            dist = self.index(sourceid) + len(self.urgentsources)
        else:
            # source id is not in the schedule, hence it is never due
            return None
        return self.starttime + td((dist + 1) * self.time_per_source)

    def is_due(self):
        """
        Returns True when it is time to call nextsample
        """
        if self.urgentsources:
            return True
        elif self.sourcequeue:
            return datetime.utcnow() >= self.due()
        else:
            return False
        
    def inject_once(self, sourceid):
        """
        Injects a source for measurement in the schedule.
        This source will not be repeated
        """
        if not (sourceid is None or sourceid in self.urgentsources):
            log(TrailerInfo('Scheduled sources:{} as single measurement'
                            .format(sourceid)))
            self.urgentsources.append(sourceid)
            return True
        else:
            return False

    def __jdict__(self):
        return AttrDict(time_per_source=self.time_per_source,
                        currentsource=self.currentsource,
                        urgentsources=self.urgentsources,
                        starttime=self.starttime,
                        schedule=self.sourcequeue,
                        pointer=self.sourcepointer,
                        events=[e.__jdict__() for e in self.events],
                        name=self.name)

    def __iter__(self):
        for soid in self.sourcequeue:
            yield soid
            
    def __len__(self):
        return len(self.urgentsources) + len(self.sourcequeue)

    def __str__(self):
        return "schedule ({}) {}/{}".format(self.name if self.name and self.sourcequeue else 'empty',
                                            len(self.urgentsources), len(self))


    def update(self, settings):
        """
        Updates the settings from a setting-dict
        """
        self.time_per_source = settings.get('time_per_source',
                                            self.time_per_source or 600)
        self.sourcequeue = settings.get('schedule', [])

        self.sourcepointer = settings.get('pointer', self.sourcepointer or 0)

        self.name = settings.get('name', self.name)
        self.save()
        self.events = [Event(**ev) for ev in settings['events']]

    def save(self, name=None):
        """
        Saves the current settings of the schedule to a json file
        """
        name = name or self.name or 'default'
        to_yaml(self.__jdict__(), name2path(name))

    def load(self, name='default'):
        """
        Loads the settings for this schedule from a json file
        """
        res = from_yaml(name2path(name))
        res['name'] = name
        self.update(res)

    def clear(self):
        """
        Clears the schedule from all scheduled tasks
        """ 
        self.sourcequeue.clear()
        self.events.clear()
        self.name = None

    @staticmethod
    def exists(name='default'):
        """
        Returns true if a schedule file with
        the name <name>.schedule.json exists
        """
        return name2path(name).exists()

    @staticmethod
    def listdir():
        """
        Returns a list of names of the saved schedules
        """
        return [path2name(p) for p in preferences_dir.glob('*.schedule.yaml')]

    @staticmethod
    def killfile(name):
        name2path(name).unlink()

