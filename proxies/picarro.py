'''
Created on 30.07.2015

@author: kraft-p
'''
import time
from numpy import random,exp
class FakePicarro(object):
    def __init__(self,variables,scantime,changerate=60):
        """
        Creates a proxy for the picarro signal
        stable: time in seconds of a stable signal
        change: time in secondes of the time to change from one signal to the other
        noise: std of noise of dH2 signal
        d2Hmax: High value of d2H
        d2Hmin: Low value of d2H 
        """
        self.active = True
        self.noise=0.5
        self.value=-50
        self.lastvalue=-50
        self.changetime = time.time()
        self.querytime = time.time()
        self.Scantime = scantime
        self.variables = variables
        self.changerate=changerate
    def __nonzero__(self):
        return self.active
    def get_status(self):
        return 963 # Is measuring and ok
    def scantime(self):
        return self.Scantime
    def is_measuring(self):
        return True
    def is_ready(self):
        return True
    def change(self,value):
        self.lastvalue = self.value
        self.value=value
        self.changetime = time.time()
    def get_result(self):
        if time.time()-self.querytime<self.scantime():
            return None
        t = time.time() - self.changetime 
        sig = 1/(1+exp(-(t-self.changerate)/(self.changerate*0.075)))
        
        d2H = self.value * sig + self.lastvalue * (1-sig)
        d18O = random.normal((d2H-10)/8 , self.noise/8.)
        d2H = random.normal(d2H,self.noise)
        H2O = random.normal(25000,500)                                                                      
        self.querytime = time.time()
        ret = dict(it for it in zip(self.variables,
                    [d18O,d2H,H2O] + 
                    ([0.0] * len(self.variables[3:])) 
                    ))
        ret['date'] = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
        return ret