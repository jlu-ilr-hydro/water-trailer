"""
Created on 26.05.2015

@author: kraft-p
"""

from __future__ import print_function
from threading import Thread
import socket
import json
import time
import numpy as np
from collections import deque, OrderedDict
import traceback

idleport = 4
verbose = False


def time2str(t):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(t))


def str2time(s):
    return time.mktime(time.strptime(s, '%Y-%m-%d %H:%M:%S'))


def neither(*args):
    return not any(args)


class CoWSError(RuntimeError):
    pass


class Sample(object):
    def __init__(self, name, port, switchtime, readytime):
        self.name = name
        self.port = int(port)
        self.switchtime = switchtime
        self.readytime = readytime
        self.starttime = None
        self.status = dict(name=name, port=port)
        self.integrationvalues = deque()
        self.is_switched = False

    def duration(self):
        return min(time.time() - (self.starttime or time.time()), self.readytime)

    def time_to_cell(self):
        return (self.readytime - self.switchtime) - self.duration()

    def time_to_switch(self):
        return self.switchtime - self.duration()

    def time_to_ready(self):
        return self.readytime - self.duration()

    def update(self):
        self.status.update(dict(progress=self.duration() / self.readytime,
                                time_to_cell=self.time_to_cell(),
                                time_to_switch=self.time_to_switch(),
                                time_to_ready=self.time_to_ready()
                                ))

    def __str__(self):
        return '{name} on port {port}, since {d:0.1f}s'.format(
            name=self.name.encode('ascii', 'replace'),
            port=self.port, d=self.duration()
        )

    def appendvalues(self, t, results, checker):
        """
        Append a result dictionary (with keys as given in variables) to the
        values for time integration
        
        This function performs the is_ready() check and returns the port to sample next 
        """
        results['time'] = t
        # Store actual results to integration set
        r = [results[v] for v in checker.variables]
        self.integrationvalues.append(r)
        # Kick out old values from integration set
        while self.integrationvalues and self.integrationvalues[0][0] < t - checker.integrationtime:
            self.integrationvalues.popleft()
        # Save integrated values to status
        self.update()
        self.status.update(self.statistics())

    def statistics(self):
        """
        Calculates the statistics for the integration time
        """
        values = np.array(self.integrationvalues)

        # Needs at least 2 values for statistic
        # Get std, mean and timespan
        tend = self.integrationvalues[-1][0]
        tstart = self.integrationvalues[0][0]

        std = np.std(values, 0)
        mean = np.mean(values, 0)

        # Timeaxis for correlation with t in seconds after tstart
        if len(values) < 2:
            return dict(n=len(values),
                        duration=tend - (self.starttime or tend))

        # Return statistic dict
        return dict(
            tstart=tstart,
            tend=tend,
            n=len(values),  # Number of values in integration time
            mean_H2O=mean[3],
            mean_d2H=mean[2],
            mean_d18O=mean[1],
            std_H2O=std[3],
            std_d2H=std[2],
            std_d18O=std[1],
            duration=tend - (self.starttime or tend)
        )


class CoWSChecker(object):
    """
    This class provides the statistics check for the CoWS coordinator
    
    Parameters for construction:
    userdata: The editParams dict from the Coordinator. Should contain 
             the following keys:
              - averaging_Time: Integration time in sec
              - duration_Calibration: Max. age for standards in min
              - standard_File: Filename to store standard measurements
              - conditions_File: File to store the conditions
    variables: the Result variables
    standards: A dict of dicts. The dicts should provide the following keys:
        - timestamp: Timestamp of the standard
        - d18O: 18O delta value in permil
        - d2H : 2H delta value in permil
        - std_d2H: Stdev of d2H
        - std_d18O: Stdev of d18O
        And the key of the holding dict should be the port
    
    Fields:
    actualsample: A dict describing the actual sample (given from outside)
    readysample: When the actualsample is_ready, actualsample is copied to readysample
    conditions: A list of conditions (s.ab.) that define, if a sample is_ready  
    integrationvalues: Measured values used in the integration. One record is stored as list
    
    """

    def __init__(self, userdata, variables):
        self.integrationtime = float(userdata['averaging_Time'])
        self.variables = ['time'] + variables
        self.readytime = float(userdata['readytime'])
        self.switchtime = self.readytime - float(userdata['switchtime'])
        global verbose
        verbose = 'y' in str(userdata['verbose']).lower()
        self.readysample = None
        self.cellsample = None
        self.linesample = None
        self.status = OrderedDict()
        self.stopped = False
        self.do_resume = False
    
    def verbose(self):
        return verbose

    def stop(self):
        return self.stopped

    def resume(self):
        if self.do_resume:
            self.do_resume = False
            return True
        else:
            return False

    def can_start(self):
        """
        Return true if the new sample can start
        """
        return not self.linesample

    def update(self):
        for n, s in zip('linesample cellsample readysample'.split(),
                        [self.linesample, self.cellsample, self.readysample]):
            if s:
                s.update()
            self.status[n] = s.status if s else s

    def startsample(self, port=3, name=None):
        """
        Starts a new sample
        """
        if self.linesample:
            raise CoWSError('Cannot start new sample, it is not time to switch')
        else:
            self.linesample = Sample(name, port, self.switchtime, self.readytime)
            self.update()
            print('Started new sample {}'.format(self.linesample))
            return 'Started new sample {}'.format(self.linesample)

    def killsample(self, name=None):
        """
        Kills the actual sample and the following sample
        """

        if name is None or name == self.cellsample.name:
            self.cellsample=None
        if name is None or name == self.linesample.name:
            self.linesample=None

    def appendvalues(self, t, results):
        """
        Append a result dictionary (with keys as given in variables) to the
        values for time integration
        
        This function performs the is_ready() check and returns the port to sample next 
        """
        self.status.update(results)
        if self.cellsample:
            self.cellsample.appendvalues(t, results, self)
        self.update()

    def setstatus(self, port, status):
        self.status.update({'currentport': port,
                            'instrstatus': status,
                            'readytime': self.readytime,
                            'switchtime': self.switchtime,
                            })

    def nextport(self, port, log):
        """
        Checks which port to use next
        """
        if self.stopped:
            return 0, 'Stopped'

        # Sample 1 is ready
        if self.cellsample and self.cellsample.time_to_ready() <= 0.0:
            log('cell sample {s} is ready'.format( s=self.cellsample))
            # Move sample to ready position
            self.readysample = self.cellsample
            self.cellsample = None

        # line sample reaches the cell
        if self.linesample and self.linesample.time_to_cell() <= 0.0:
            log('line sample {} reaches cell'.format(self.linesample))
            if self.cellsample:
                log('     WARNING: cell sample {} not ready yet, but popped out of line'.format(self.cellsample))
            # Line sample becomes cellsample
            self.cellsample = self.linesample
            # Line sample is obsolete
            self.linesample = None

        # Update samples
        if self.linesample:
            self.linesample.update()
        if self.cellsample:
            self.cellsample.update()

        # Cell sample can switch to idle
        if self.cellsample and self.cellsample.time_to_switch() <= 0.0 and not self.cellsample.is_switched:
            self.cellsample.is_switched = True
            log('{} switches to idle'.format(self.cellsample))
            return idleport, 'Idle'

        # No cell sample, no line sample -> idle
        elif neither(self.cellsample, self.linesample):
            if port != idleport or verbose:
                log('{}: no active sample, idle port ({}), {} ready'
                    .format(time.ctime(), idleport, self.readysample))
            # No active sample
            return idleport, 'Idle'

        # If idle and a new sample is started, move the port there
        elif port == idleport and self.linesample:
            log('now idle, move to {}'.format(self.linesample, self.readysample))
            self.linesample.starttime = time.time()
            return self.linesample.port, 'Idle'

        # If a cellsample is active
        elif self.cellsample:
            if verbose:
                log('port {}, measure {}, {} ready, {} in line'.format(port, self.cellsample,
                                                                         self.readysample, self.linesample))
            return port, self.cellsample.name.encode('ascii', 'replace')

        # else no cell sample but a line sample active but still not in cell
        elif self.linesample:
            if verbose:
                log('port {} line:{} {:0.1f}s to cell, {} in cell, {} ready'
                    .format(port, self.linesample, self.linesample.time_to_cell(),
                            self.cellsample, self.readysample))
            return self.linesample.port, self.linesample.name.encode('ascii', 'replace')

        else:
            # Should not happen
            log('ERROR! Uncovered situation on port {}!'.format(port))
            for n, s in zip('line cell ready'.split(), [self.linesample, self.cellsample, self.readysample]):
                log('    {}: {}'.format(n, s))
            return idleport, 'error'


def recv(sock, chunk=1024):
    """
    Helper function to simplify socket receiving of arbitrary sized data chunks
    Used by CoWSCommunicator
    """

    def recvgen():
        while True:
            s = sock.recv(chunk)
            if s:
                yield s
                if len(s) < chunk:
                    break
            else:
                break

    return ''.join(recvgen())


class CoWSCommunicator(Thread):
    """
    This class communicates the results of the checker with json over a socket server.
    The communication protocol is a tuple of [command (unicode),message (unicode), data (dict)]
    
    Commands available:
    sample: Sets a new sample for measurements. 
            Returns error if CoWS is already sampling. data needs at least a name key
    status: Returns in data two dictionaries: sample contains the sample properties, 
            and status the state of the conditions

    
    """

    def __init__(self, checker, tcpport=51211):
        Thread.__init__(self)
        self.checker = checker
        self.tcpport = tcpport

    def stop(self):
        self.checker = None

    def log(self, something):
        pass

    def run(self):
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.bind(('0.0.0.0', self.tcpport))
        serversocket.listen(1)
        while self.checker:
            sock = None
            try:
                sock, addrinfo = serversocket.accept()
                self.log(addrinfo)
            except socket.error:
                if sock:
                    sock.close()
                continue
            # Revieve up to 1K data
            s = recv(sock, 1024)
            if not s:  # if nothing received, return None
                return None
            # get command of msg
            try:
                # Decode msg-object
                cmd, data = json.loads(s.decode(encoding='utf-8', errors='replace'))
            except EOFError:
                print(s)
                sock.close()
                continue
            if cmd.strip() == '?':
                res = self.do_status()
            elif hasattr(self, 'do_' + cmd):
                try:
                    res = getattr(self, 'do_' + cmd)(**data)
                except Exception as e:
                    res = {'error': repr(e)}
            else:
                res = {'error': 'Unknown command "{}" '.format(cmd)}
            s = json.dumps(res, ensure_ascii=False)
            sock.sendall(s.encode('utf-8'))
            sock.close()

    def do_status(self):
        return self.checker.status

    def do_killsample(self, name=None):
        self.checker.killsample(name)
        return self.do_status()

    def do_sample(self, name, port):
        try:
            result = self.checker.startsample(port, name)
        except CoWSError:
            return dict(error='CoWS is not free', **self.do_status())
        else:
            return dict(message=result, **self.checker.status)
            
    def do_setparameters(self, integrationtime=None, switchtime=None, readytime=None): #, verbose=None):
        try:
            if integrationtime is not None:
                self.checker.integrationtime = float(integrationtime)
            if switchtime is not None:
                self.checker.switchtime = float(switchtime)
            if readytime is not None:
                self.checker.readytime = float(readytime)
            #if verbose is not None:
            #    global verbose
            #    verbose = bool(verbose)
        except:
            return {'cmd': 'setparameters',
                    'error': traceback.format_exc()
                    }
        else:
            return {'cmd': 'setparameters',
                    'integrationtime': self.checker.integrationtime,
                    'switchtime': self.checker.switchtime,
                    'readytime': self.checker.readytime,
                    #'verbose': verbose
                    }
            
            

    def do_stop(self):
        self.checker.stopped = True
        return self.checker.status
