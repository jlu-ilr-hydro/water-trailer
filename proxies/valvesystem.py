'''
Creates an High-Level API for the valve system for sampling of the trailer, as a proxy system
for off-line debugging

Uses the alpha2 lib to communicate with the PCL

Created on 08.06.2015

@author: kraft-p
'''
from __future__ import division
import time
from trailer.devices import DeviceError, DeviceWarning, Device
class Scale(object):
    """
    The reservoir scale of the valvesystem. The scale object stores
    calibration values to calculate actual weight from the digital units of the pcl
    """
    
    
    def __init__(self,w0kg,w1kg):
        self.offset = float(w0kg)
        self.slope = float(w1kg - w0kg)
    def du2kg(self,du):
        return (du - self.offset)/self.slope 
    def kg2du(self,kg):
        return kg * self.slope + self.offset

class Status(object):
    """
    This class holds the status of the valvesystem, directly read from the Alpha2 PCL.
    On creation, the PCL is read and the result is parsed against error conditions and 
    the current action is determined. There is a great number of states, the most important
    ones are these:
    
    - action: The current action (flush,fill,empty)
    - running: True if the action is still running (eg. Pump is running, reservoirvalve is open)
    - time: The current time in seconds since epoch (time.time)
    - errors: A list of detected errors
    - actvol_kg: The actual content of the reservoir in kg
    - tgtvol_kg: The target content of the reservoir in kg
    """
    
    nicenamedict = dict(
                        actvol_du='Actual volume [DU]',
                        tgtvol_du='Target volume [DU]',
                        actvol_kg='Actual volume [kg]',
                        tgtvol_kg='Target volume [kg]',
                        timeout='Timeout [s]',
                        elapsed='Elapsed time [s]',
                        time='Status time since epoch [s]',
                        action='Action',
                        running='Action active',
                        pumpfwd='Pump running',
                        reservoir='Reservoir valve open',
                        wastevalve='Sample to reservoir',
                        fridgevalve='fridgevalve open',
                        fridgebit='Sample to fridge',
                        channel='Requested channel',
                        channel_open='Requested channel open',
                        )
    def __init__(self,valvestate):
        self.action=None
        self.running = False
        self.errors=[]
        self.time = time.time()

        # Fake Status
        self.actvol_du,self.tgtvol_du,self.flushtime,self.filltime,self.emptytime = [77,127,60,300,300]
        self.flushbit,self.fillbit,self.emptybit,self.waterwarning1,self.waterwarning2,self.stopbit = [False] * 6
        self.pumpfwd,self.reservoir,self.wastevalve, self.fridgevalve = [False,False,True,False]
        self.valvestate=dict((i,(False,False)) for i in range(11,45))
        self.actvol_kg=0.0
        self.tgtvol_kg=0.5
        self.channel_open = False
        self.channel=0
        
        # Detect common error states      
        if self.waterwarning1:
            self.errors.append('Water at detector 1')
        if self.waterwarning2:
            self.errors.append('Water at detector 2')
        if sum([self.fillbit,self.flushbit,self.emptybit])>1:
            self.errors.append('More than one program bit has been set')
        
        # Check program
        if self.flushbit:
            # Flush
            self.action = 'flush'
            self.running = self.pumpfwd
        elif self.fillbit:
            # Fill
            self.action = 'fill'
            self.running = self.pumpfwd
        elif self.emptybit:
            self.action = 'empty'
            self.running = self.reservoir
    def __repr__(self):
        return 'Status(action={action},channel={channel},actvol_kg={actvol_kg:g},tgtvol_kg={tgtvol_kg:g}'.format(**vars(self))
    def __str__(self):
        d=vars(self)
        return 'Status of pcl:\n'+'\n'.join('{:<30}: {}'.format(Status.nicenamedict[k],d[k]) for k in Status.nicenamedict)    
    def canflush(self):
        return not (self.action == 'fill' and self.running)
    def canfill(self):
        return not (self.action in ['flush','empty'] and self.running)
    def canempty(self):
        return not (self.action=='fill' and self.status.running)
    def progress(self,startvol=0):
        if self.flushbit and self.timeout:
            return self.elapsed / self.timeout
        elif (self.fillbit or self.emptybit) and (abs(self.tgtvol_kg-startvol)>0.01):
            return (self.actvol_kg-startvol) / (self.tgtvol_kg-startvol)
        else:
            return 0.0
            
            
            
        
class ValveSystem(Device):
    def __init__(self,pcl,valveblocks=3):
        self.pcl = pcl
        self.scale = Scale(84,177)
        self.action=None
        self.readstatus()
        self.defaulttimeout=60
        self.startvol = self.status.actvol_kg
        self.targetvol = self.status.tgtvol_kg
        self.statustimeout = 0.1
        self.valveblocks = valveblocks
    def reset(self):
        """
        Closes all valve request, kills all programs
        """
        self.pcl.write.I(13,True).send()
        self.action=None
        
    def flush(self,sourceid,timeout=60):
        """
        Starts the flush program on the PCL.
        """

        st = self.readstatus()
        self.startvol = st.actvol_kg
        if not st.canflush():
            raise DeviceError('Flush is blocked by {}. Wait until it finishes'.format(st.action),self)
        self.reset()
        block,valve = sourceid // 10, sourceid % 10        
        # set valves
        self.pcl.write.CW(10,block).CW(11,valve).send()
        # set timeout
        self.pcl.write.CW(2,int(timeout)).send()
        self.pcl.write.I(10,True).send()
        # Refresh the status
        st=self.readstatus()
        if st.action!='flush' or not st.running:
            self.reset()
            raise DeviceError('Flush requested, but flush has not started',self)
        self.action=st.action
    def fill(self,sourceid,volume=0.3,timeout=None):
        """
        Starts the fill program on the PCL.
        """
        timeout = timeout or self.defaulttimeout
        st=self.readstatus()
        self.startvol = st.actvol_kg
        if not st.canfill():
            raise DeviceError('Fill is blocked by {}. Wait until it finishes'.format(st.action),self)
        self.reset()
        block,valve = sourceid // 10, sourceid % 10        
        # set valves
        self.pcl.write.CW(10,block).CW(11,valve).send()
        # Set target volume 
        self.pcl.write.CW(1,self.scale.kg2du(volume)+0.5).send()
        # set timeout
        self.pcl.write.CW(2,int(timeout)).send()
        # Set fill bit (I11)
        self.pcl.write.I(11,1).send()
        # Refresh the status
        st=self.readstatus()
        if st.action!='fill' or not st.running:
            self.reset()
            raise DeviceError('Fill requested, but fill has not started',self)
        self.action=st.action
    def empty(self,volume=1e6,timeout=None,tofridge=False):
        """
        Starts the empty program on the PCL.
        
        tofridge: If set to True
        """
        timeout = timeout or self.defaulttimeout
        st=self.readstatus()
        self.startvol = st.actvol_kg
        if not st.canempty():
            raise DeviceError('Empty is blocked by {}. Wait until it finishes'.format(st.action),self)

        self.reset()
        # calculate target volume
        tgtvol = max(0,self.status.actvol_kg-volume)

        # Set target volume 
        self.pcl.write.CW(1,self.scale.kg2du(tgtvol)-0.5).send()
        # Set timeout
        self.pcl.write.CW(2,int(timeout)).send()

        if bool(tofridge) != bool(st.fridgebit):
            # Toggle the fridge request if it does not fit your wishes
            self.pcl.write.I(9,True).send()
        # Set empty bit (I 12)
        self.pcl.write.I(12,1).send()
        # Refresh the status
        st=self.readstatus()
        if st.action!='empty':
            self.reset()
            raise DeviceError('Empty requested, but empty has not started',self)
        self.action=st.action
    def emptycomplete(self,timeout=None):
        timeout = timeout or 5
        self.reset()
        st=self.readstatus()
        self.pcl.write.CW(1,self.scale.kg2du(0.0)-5).send()
        self.pcl.write.CW(2,int(timeout)).send()
        self.pcl.write.I(12,1).send()
        self.action=st.action
    
    def is_ready(self):
        """
        Reads the status if the status is old
        Returns:
            False,'' if the current action is still running
            True,'' if the current action has finished appropiatly
            True,Message if the current action has finished but not 
                    with problems
                    
        This method is thread-safe as it does no reading of the PCL.
        Please make sure that the saved status is not to old
        """
        st=self.status
        res = True
        if self.action is None and st.action is None:
            # system is idle
            pass
        elif st.action == self.action:
            if st.running:
                # Action is not finished but running
                res = False
            else:
                DeviceWarning('{} still active on PCL, but actor is not running. Check for errors.'.format(self.action),self)
        elif st.action is None:
            if self.action == 'flush':
                if st.elapsed<st.timeout:
                    DeviceWarning('flush stopped by error or reset',self)
            elif self.action in ['empty','fill']:
                if st.elapsed>=st.timeout:
                    DeviceWarning('{} stopped due to timeout'.format(self.action),self)
                elif abs(st.actvol_du -st.tgtvol_du)>1:
                    DeviceWarning('{} stopped before timeout, with {:0.3f}l content, while {:0.3f}l expected'.format(self.action,st.actvol_kg,st.tgtvol_kg))
            else:
                raise DeviceError('System has unknown action {}'.format(self.action),self)
        else:
            raise DeviceError('Action of system is {} but PCL runs program {}'.format(self.action,st.action),self)
        return res            
        
    def readstatus(self):
        """
        Reads the status from the pcl
        """
        self.status= Status(self)
        if self.status.errors:
            raise DeviceError(', '.join(self.status.errors),self)
        return self.status
    @property
    def data(self):
        return vars(self.status)
    def progress(self):
        return self.status.progress(self.startvol) 
    def itervalveids(self):
        for block in range(self.valveblocks):
            for valve in range(4):
                yield (block + 1) * 10 + (valve + 1)          
class ValveSystemRead(object):
    def __init__(self,valvesystem):
        self.__valvesystem = valvesystem
    @property
    def status(self):
        return self.__valvesystem.status
    def is_ready(self):
        return self.__valvesystem.is_ready()

class ValveSystemFake(object):
    status = Status(None)
    prog=0.0
    @classmethod
    def reset(cls):
        return None
    @classmethod
    def progress(cls):
        cls.prog = (cls.prog + 0.02) % 1
        return cls.prog


if __name__=='__main__':
    from .alpha2 import connect
    with connect(port='COM1',timeout=0.5) as pcl:
        #pcl.debug=True
        print 'PCL OK:',pcl.test()
        print 'Run:',pcl.runprogram()
        vs = ValveSystem(pcl)
        vsw = ValveSystemWindow(vs)
        vsw.start()

