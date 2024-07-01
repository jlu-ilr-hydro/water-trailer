'''
Created on 26.05.2015

@author: kraft-p
'''
from threading import Thread
import os
import socket
import json
import time
import numpy as np
from collections import  deque
from scipy.stats import pearsonr

def time2str(t):
    return time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(t))
def str2time(s):
    return time.mktime(time.strptime(s,'%Y-%m-%d %H:%M:%S'))
class IsotopeStandard(object):
    """
    Describes an IsotopeStandard source
    """
    def __init__(self,name,port,d18Oreal,d2Hreal,d18Omeas,d2Hmeas,measuretime=None,**kwargs):
        self.name=name
        self.port=port
        self.d2Hreal = d2Hreal
        self.d18Oreal = d18Oreal
        self.d18Omeas = d18Omeas
        self.d2Hmeas = d2Hmeas
        self.measuretime = measuretime or time.time()
        self.conditions = kwargs
    @property
    def timestr(self):
        return time2str(self.measuretime)
    def update(self,d18Omeas,d2Hmeas,**kwargs):
        distance = d18Omeas-self.d18Omeas, d2Hmeas - self.d2Hmeas
        self.measuretime = time.time()
        self.d18Omeas, self.d2Hmeas = d18Omeas, d2Hmeas
        self.conditions.update(kwargs)
        return distance
    def describe(self,inunicode=True):
        if inunicode:
            return u"""Standard %s:
                   Real:     \u03B4\u00B9\u2078O=%g\u2030, \u03B4\u00B2H=%g\u2030
                   Measured: \u03B4\u00B9\u2078O=%g\u2030, \u03B4\u00B2H=%g\u2030
                   Time:     %s""" % (self.name,self.d18Oreal,self.d2Hreal,
                                      self.d18Omeas,self.d2Hmeas,self.timestr)
        else:
            return """Standard %s:
                   Real:     d18O=%g%%o, d2H=%g%%o
                   Measured: d18O=%g%%o, d2H=%g%%o
                   Time:     %s""" % (self.name,self.d18Oreal,self.d2Hreal,
                                      self.d18Omeas,self.d2Hmeas,self.timestr)

    def __repr__(self):
        return "IsoStd(%s)" % self.name
    def __str__(self):
        return "Standard %s: d18O=%g%%o, d2H=%g%%o" % (self.name,self.d18Oreal,self.d2Hreal)
    def __unicode__(self):
        return u"Standard %s: \u03B4\u00B9\u2078O=%g\u2030, \u03B4\u00B2H=%g\u2030" % (self.name,self.d18Oreal,self.d2Hreal)
    def __getitem__(self,index):
        return [self.d18Oreal,self.d2Hreal,self.d18Omeas,self.d2Hmeas][index]
    def save(self,filename=None):
        self.filename = filename
        if not os.path.exists(filename):
            f=open(filename,'wb')
            f.write('Name,port,d18Oreal,d2Hreal,d18Ocell,d2Hcell,Measuretime\n')
        else:
            f=open(filename,'ab')
        d = vars(self)
        d.update(time=self.timestr)
        f.write('%(name)s,%(port)i,%(d18Oreal)g,%(d2Hreal)g,%(d18Omeas)g,%(d2Hmeas)g,%(time)s\n' % d)


class IsotopeCalibration(list):
    """
    A list of IstopeStandard objects with a function for calibration
    """
    filename='standards.csv'
    def get_linregvalues(self):
        d18Oreal,d2Hreal,d18Omeas,d2Hmeas = zip(*self)
        dOa,dOb = np.polyfit(d18Omeas,d18Oreal,1)
        dHa,dHb = np.polyfit(d2Hmeas,d2Hreal,1)
        return dOa,dOb,dHa,dHb
    def calibrate(self,d18O,d2H):
        if len(self)<2:
            raise RuntimeError("Cannot calibrate a value with less than 2 standards")
        
        dOa,dOb,dHa,dHb = self.get_linregvalues()
        return dOa * d18O + dOb, dHa * d2H + dHb 
    def __str__(self):
        return ('Standards:\n' + '\n'.join('    %s' % s for s in self) +
                "\nCalibration:\n    d18O=%6.3g d18O'+%6.3g\n    d2H =%6.3g d2H' +%6.3g" % self.get_linregvalues())
    def __unicode__(self):
        return 'Standards:\n' + '\n'.join(u'    %s' % s for s in self)
    def outdated(self,timeout):
        now = time.time()
        return any(std.measuretime + timeout<now for std in self)
    @classmethod
    def load(cls,filename):
        """
        Loads standard descriptions from a csv file
        """
        f = open(filename)
        f.readline() # skip headers
        standards={}
        for l in f:
            if l.strip() and l.strip()[0]!='#':
                name, port, d18Oreal,d2Hreal,d18Ocell,d2Hcell,time = l.split(',')
                port=int(port)
                std= IsotopeStandard(name,port, 
                                     float(d18Oreal),float(d2Hreal),
                                     float(d18Ocell),float(d2Hcell),
                                     str2time(time.strip()))
                
                if (not port in standards) or std.measuretime>standards[port-1].measuretime:
                    standards[port-1] = std                
                
        me = cls()
        me.filename = filename
        me.extend(sorted(standards.itervalues(),key=lambda std:std.id))
        return me


class Condition(object):
    """
    Condition object test a variable from a dictionary for a boolean expression.
    The boolean expression needs to be valid Python syntax and the variable
    """
    def __init__(self,condition,X,name):
        """
        Creates a new condition
         - condition is a python expression including 'X' as a test variable, eg. 'X>0'. 
           The expression needs to be self contained (no other dependencies)
         - X the name of the variable. Is used to get the variable X from a dictionary
         - name is a docstring of the condition  
        """
        self.conditiontext = condition
        try:
            self.condition=eval('lambda X:' +condition,vars(np))
        except Exception as e:
            raise ValueError('Your condition is not valid Python code, got %s on evaluation' % e)
        self.X=X
        self.name=name
    def __call__(self,d):
        """
        Tests the condition using the dictionary d. d should contain X
        """
        return self.condition(d.get(self.X,np.nan))
    def __repr__(self):
        return '%s with X=%s -> %s' % (self.conditiontext,self.X,self.name)
    @classmethod
    def parse(cls,line):
        if not ' with X=' in line:
            raise ValueError('Cannot parse condition from "%s". Missing " with X="' % line)
        ct,rest = line.split(' with X=')
        if '->' in rest:
            X,name = rest.split('->')
        else:
            X=rest,name=ct.replace('X',X)
        return cls(ct.strip(),X.strip(),name.strip())
    @classmethod
    def writeall(cls,fn,conditions):
        with open(fn,"w") as f:
            f.write('# Statistical conditions to be met, when a sample is assumed to be ok\n')
            for c in conditions:
                f.write('{}\n'.format(c))
def logger(logfile):
    if logfile:
        with open(logfile,'a') as lf:
            while True:
                msg = yield
                if not msg:
                    break
                lf.write(time2str(time.time()) + '\t' + msg + '\n')
    else:
        while True:
            msg = yield
            if not msg:
                break
            

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
    
    Fields:
    actualsample: A dict describing the actual sample (given from outside)
    readysample: When the actualsample is_ready, actualsample is copied to readysample
    conditions: A list of conditions (s.ab.) that define, if a sample is_ready  
    integrationvalues: Measured values used in the integration. One record is stored as list
    
    """
    def __init__(self,userdata,variables):
        self.logfile='ilrlog.txt'
        log = logger(self.logfile)
        log.next()
        log.send('init: checker started')
        self.integrationtime = float(userdata.get('averaging_Time',120))
        self.variables = ['time'] + variables
        log.send("\n".join("{}:{}".format(*it) for it in enumerate(self.variables)))
        self.integrationvalues = deque()
        self.standardtimeout = float(userdata.get('duration_Calibration',20))*60.0 
        self.actualsample={}
        self.readysample={}
        self.standards = IsotopeCalibration()
        if 'standard_File' in userdata and os.path.exists(userdata['standard_File']):
            self.standards = IsotopeCalibration.load(userdata['standard_File'])
        try:
            self.conditions = [Condition.parse(line) 
                               for line in open(userdata['conditions_File']) 
                               if not line.strip().startswith('#')
                               ]
        except:
            self.conditions=[Condition('X>30','duration','Minimum time to result'),
                 Condition('X>20','n','Minimum n'),
                 Condition('X**2<0.005**2','slope_d18O','Maximum allowed slope d18O'),
                 Condition('X**2<0.01**2','slope_d2H','Maximum allowed slope d2H'),
                 Condition('X>15000','mean_H2O','Minimum water concentration')]
            Condition.writeall(userdata.get('conditions_File','condition.txt'), self.conditions)
    def is_ready(self,detailed=False):
        """
        Returns true if the ready condition in __is_ready is fullfilled. 
        If detailed is True, a dictionary is returned with the conditions' X as key and True/False
        for the condition status 
        """
        conditions = [c(self.actualsample) for c in self.conditions] 
        try:
            iter(conditions)
        except:
            self.logger('Got not a list of conditions from is_ready',self.__module__,3)
            conditions=[False] * len(self.conditions)
        if detailed:
            return dict((c.X,c_eval) for c,c_eval in zip(self.conditions,conditions)) 
        return all(conditions)
    def startsample(self,sampledict={},**kwargs):
        log = logger(self.logfile)
        log.next()
        kwargs.update(sampledict)
        if not 'name' in kwargs:
            kwargs['name']='unknown'
        log.send('startsample: Start sample {}'.format(kwargs))
        self.actualsample = kwargs
        self.actualsample['samplestart']=time.time()
        self.readysample={}
        self.integrationvalues.clear()
    def statistics(self):
        """
        Calculates the statistics for the integration time
        """
        values = np.array(self.integrationvalues)

        # Needs at least 2 values for statistic
        if len(values)<2:
            return dict(n=len(values),samplestart=self.integrationvalues[0][0])
        # Get std, mean and timespan
        tend = self.integrationvalues[-1][0]
        tstart = self.integrationvalues[0][0]
        
        std = np.std(values,0)
        mean =np.mean(values,0)
        
        # Timeaxis for correlation with t in seconds after tstart
        timeaxis = [(v[0]-tstart) for v in self.integrationvalues]
        
        # Return statistic dict
        return dict(
            tstart = tstart,
            tend=tend,
            n=len(values), # Number of values in integration time
            r2_d18O= pearsonr(timeaxis, values[:,1])[0]**2,
            r2_d2H = pearsonr(timeaxis, values[:,2])[0]**2,
            r2_H2O = pearsonr(timeaxis, values[:,3])[0]**2,
            slope_d18O = np.polyfit(timeaxis, values[:,1],1)[0],
            slope_d2H = np.polyfit(timeaxis, values[:,2],1)[0],
            slope_H2O = np.polyfit(timeaxis, values[:,3],1)[0],
            mean_H2O=mean[3],
            mean_d2H=mean[2], 
            mean_d18O=mean[1], 
            std_H2O=std[3],
            std_d2H=std[2],    
            std_d18O=std[1], 
            duration = tend-self.actualsample['samplestart']
        )
    def appendvalues(self,t,port,results):
        """
        Append a result dictionary (with keys as given in variables) to the
        values for time integration
        
        This function performs the is_ready() check and returns the port to sample next 
        """
        log = logger(self.logfile)
        log.next()
        results['time'] = t
        # Store actual results to integration set
        r = [results[v] for v in self.variables]
        self.integrationvalues.append(r)
        # Kick out old values from integration set
        while self.integrationvalues and self.integrationvalues[0][0]<t - self.integrationtime:
            self.integrationvalues.popleft()
        if self.actualsample:
            self.actualsample.update(self.statistics())
            self.actualsample['port']=port
            return self.actualsample
        else:
            return {}
    def nextport(self,port):
        log = logger(self.logfile)
        log.next()
        if not self.actualsample:
            if port==4 and self.standards.outdated(self.standardtimeout):
                # Sample standards
                self.startsample(name=self.standards[0])

                return 1
            else:
                log.send('nextport: idle on port 3')
                return 3
        if self.is_ready() and self.actualsample:
            
            log.send('nextport: {name} is ready'.format(**self.actualsample))
            log.send('nextport: {}'.format(self.is_ready(True)))
            if port == 4: # Sample line
                # Store actual sample as ready sample
                self.readysample = self.actualsample.copy()
            else:
                # If standard is ready, get standard from port no.
                std = self.standards[port-1]
                # Update standard
                std.update(self.actualsample['mean_d18O'],
                            self.actualsample['mean_d2H'],
                            self.actualsample)
                std.save()
            # Mark cell as idle
            self.actualsample = {}
            # Clear integrationvalues
            self.integrationvalues.clear()
            # If sample line active (4)
            # and any standard is outdated
            if port==4 and self.standards.outdated(self.standardtimeout):
                # Sample standards
                log.send('nextport: Start sampling standard 1')
                self.startsample(name=self.standards[0])
                return 1
            # If sampling standards, go to next standard or sampling line
            elif port<len(self.standards):
                log.send('nextport: Start sampling standard {}'.format(port+1))
                self.startsample(name=self.standards[port])
                return port + 1
            else: # in any other case go to sample line
                log.send('nextport: Return to sample line')
                return 4
        else: # idle, proceed with current port
            log.send('nextport: {}'.format(self.actualsample))
            return port or 4


def recv(sock,chunk):
    """
    Helper function to simplify socket receiving of arbitrary sized data chunks
    Used by CoWSCommunicator
    """
    def recvgen():
        while True:
            s = sock.recv(chunk)
            if s:
                yield s
                if len(s)<chunk:
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
    conditions: Sets the conditions. Data needs to have a field conditions which contains a condition text (cf. Condition class)
     
    
    """
    def __init__(self,checker,tcpport=51211):
        Thread.__init__(self)
        self.checker=checker
        self.tcpport = tcpport
    def stop(self):
        self.checker=None
    def log(self,something):
        pass
    def run(self):
        serversocket = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        serversocket.setblocking(0)
        serversocket.bind(('0.0.0.0',self.tcpport))
        serversocket.listen(1)
        while self.checker:
            sock = None
            try:
                sock,addrinfo = serversocket.accept()
                self.log(addrinfo)
            except socket.error:
                if sock:
                    sock.close()
                continue
            sock.setblocking(1)
            # Revieve up to 1K data
            s = recv(sock,1024)
            if not s: # if nothing recieved, return None 
                return None
            # get command of msg
            try:
                # Decode msg-object
                cmd,msg,data = json.loads(s)
            except EOFError:
                print s
                sock.close()
                continue
            
            if hasattr(self,'do_'+cmd):
                try:
                    res=getattr(self,'do_' + cmd)(**data)
                except Exception as e:
                    res = 'error',e.msg,{}
            else:
                res = 'error','Unknown command "{}" in message "{}"'.format(cmd,msg),{}
            s=json.dumps(res,ensure_ascii=False)
            sock.sendall(s)
            sock.close()

    def do_conditions(self,conditions=''):
        if conditions:
            conditions = [Condition.parse(line) for line in conditions.split('\n')]
            self.checker.conditions = conditions
        return 'response','conditions',dict(('c%i' % i,'%s' % c) for i,c in enumerate(self.checker.conditions))
    def do_status(self):
        return 'response','status',dict(time=time.time(),
                                        sample=self.checker.actualsample,
                                        readysample=self.checker.readysample,
                                        status=self.checker.is_ready(True))
    def do_killsample(self):
        oldsample = self.checker.actualsample.copy()
        self.checker.actualsample={}
        return 'response','Killed sample {}'.format(oldsample['name']),oldsample
    def do_sample(self,**sample):
        if self.checker.actualsample:
            return 'error','CoWS has a sample already',self.checker.actualsample
        else:
            self.checker.startsample(**sample)
            return 'response','CoWS got new sample',self.checker.actualsample
class DeviceResend(Exception):
    pass
class DeviceError(Exception):
    pass   
class SimpleClient(object):
    def __init__(self,picarrohost='localhost',tcpport=51211):
        self.picarroadress = (picarrohost,tcpport)
        self.status = {}
        self.actsample = {}
        self.data={}
    def send(self,command,message='',**data):
        sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        sock.settimeout(None)
        sock.connect(self.picarroaddress)
        req = json.dumps([command,message,data])
        sock.sendall(req)
        #time.sleep(0.1)
        answer = recv(sock,1024)
        if not answer:
            raise DeviceResend('Picarro at {} does not respond'.format(self.adress),self)
        try:
            cmd,msg,data = json.loads(answer)
        except:
            raise DeviceError('Got answer that is not understood as cmd,msg,data in json: {}'.format(answer),self)
        return cmd,msg,data
    def readstatus(self):
        cmd,msg,data = self.send('status')
        if cmd!='response' or msg!='status':
            raise DeviceError('Picarro answered not as expected: {},{},{}'.format(cmd,msg,data),self)
        self.actsample = data['sample']
        self.status = data['status']
        if data.get('readysample'):
            self.data = data.get('readysample')
    def is_ready(self):
        return bool(self.data)
    def startsample(self,name):
        cmd,msg,data = self.send('sample',name=name)
        if cmd=='error':
            raise DeviceError(msg,self)
        self.data={}
        self.actsample = data
    def setconditions(self,conditiontext=''):
        cmd,msg,data = self.send('conditions',conditions=conditiontext)
        if cmd=='error':
            raise DeviceError(msg)
        else:
            return data


def testbyfile(integtime=120.0):
    # A unit test based on CoWS results in a file
    userdata = {'averaging_Time':integtime}
    variables = ["Delta_18_16", "Delta_D_H", "H2O", "CH4", "baseline_shift", "baseline_curvature", "slope_shift", "residuals"]
    rowvars = ['d(18_16)','d(D_H)','Water_ppm','Methane_ppm', "baseline_shift", "baseline_curvature", "slope_shift", "residuals"]
    checker = CoWSChecker(userdata,variables)
    
    import glob
    print os.path.abspath('.')
    print 'Files: ' + ','.join(glob.glob('*.csv'))
    import pandas as pd
    data=pd.read_csv(glob.glob('HID*.csv')[0],sep=',',skipinitialspace=True,index_col=0)
    print '\n'.join(data.columns)
    
    outfile=open('pkintegration.csv','w')
    outvars=['name','port','tstart','tend','n',
             'r2_H2O','r2_d2H','r2_d18O',
             'slope_H2O','slope_d2H','slope_d18O',
             'mean_H2O','mean_d18O','mean_d2H',
             'std_H2O','std_d18O','std_d2H',
             'duration','ready']
    outfile.write(','.join(outvars) + '\n')
    for index,row in data.iterrows():
        port =int(float(row.Inlet_Port.split()[-1]))
        if port != checker.actualsample.get('port'):
            checker.startsample(name=row.Sample_Type,port=port)
        rowtrans = dict((vv,row[rv]) for vv,rv in zip(variables,rowvars))
        sample=checker.appendvalues(row['End_Time']*60., port, rowtrans)
        sample['ready'] = int(checker.is_ready(False))
        #print ','.join('{}'.format(sample.get(k,np.nan)) for k in outvars)
        if sample['n']>2:
            outfile.write(','.join('{}'.format(sample.get(k,np.nan)) for k in outvars) + '\n')
        if index % 1000 == 0:
            print index

if __name__ == '__main__':
    import sys
    client = SimpleClient()
    if len(sys.argv)>1:
        client.startsample(sys.argv[1])
    status=client.readstatus()
    print 'Actual sample:\n','\n'.join('   {}:{}'.format(k,v) for k,v in client.actsample.iteritems())
    print 'Ready sample:\n','\n'.join('   {}:{}'.format(k,v) for k,v in client.data.iteritems())
    print 'Status:\n','\n'.join('   {}:{}'.format(k,v) for k,v in client.status.iteritems())
        
        
      
        
        
    
'''
Created on 28.07.2015

@author: kraft-p
'''
