import sys
import time
from time import sleep


"""
Start Philipp's code to replace the calls to the Picarro software

This file is a mess, I know. Picarro decided to mix data and code in .ini files, 
hence it is not possible to debug the final .ini file with python tools.
This file is a valid python 2.7 program that consists of the content of the ini file 
and additional code to make it running. The additional code tries to mimic the anticipated
behaviour of the proprietary Picarro runtime. When this code runs under simulated conditions
a working .ini file is extracted from this program. To do so, this file is splitted using the 
splitsymbol as defined below and only the odd sections are copied to the ini file and the even
sections are discarded. This text here is in section 0 and is therefore not copied. The splitting
technique is in some parts a bit weird to account for parts to be used in the  ini file and that 
are not valid python code. A good example for that is the next section. Multiline quotation before
the splitsymbol is used to prevent the next section to be interpreted as python code.
"""
# First the symbol to split the code to create the ini. The symbol is written in a form,
# that is not recognized by the parser but has the right meaning
splitsymbol='#' + '@' + '-'

# First some text to be copied into the ini
"""
#@-
        # Coordinator for CoWS (Continuous Water Samplers) using the HIDS analyzer
        
        [UserEditableParams]
        num_disp_params = 0
        {editParams}
        
        [Mode]
        inject_mode = automatic
        
        [Archiver]
        archiveGroupName = Coordinator
        
        [Files]
        output = "c:/IsotopeData/IsoWater_CoWS"
        log = "c:/IsotopeData/Log/Log_CoWS"
        
        [Output]
        line_Num                     = "Line",%20d
        startLocal                   = "Time", %22s
        time                         = "Time_since_start", %15s
        sample_Inlet_Port            = "Inlet_Port", %10i
        sample_name                  = "Sample", %15s
        Delta_18_16                  = "d(18_16)",%20.3f
        Delta_D_H                    = "d(D_H)",%20.3f
        H2O                          = "Water_ppm", %20.3f
        water_Temperature            = "Water_Temp_C", %50s
        ePTFE_Temperature            = "Membrane_Temp_C", %20s
        trans_Temperature            = "Transfer_Line_Temp", %20s
        air_Temperature              = "Air_Temp", %20s        
        air_FlowRate                 = "Air_Flow_Rate_sccm", %20s
        PID_loops_locked             = "PID_loops_locked", %5s
        CH4                          = "Methane_ppm", %20.3f
        baseline_shift               = "baseline_shift",%14.3f
        baseline_curvature           = "baseline_curvature",%14.3f
        slope_shift                  = "slope_shift",%14.3f
        residuals                    = "residuals", %14.3f
        
        [Setup]
        initial=StateSetupCoWS
        final=StateDone
        error=StateError
#@-
"""
sys.path.append('..')

# In this section we define the functions used from the Picarro API. The ini file uses them,
# and here we define the functions/classes with the minimal needed behaviour

def logFunc(msg):
    """
    Usage in Picarro Software: Displays the message in the coordinator window
    Replacement: Prints to the console
    """
    sys.stdout.write(msg)
class InstMgrFake:
    """
    A faking status provider, returns always 963 which means everything is fine
    """
    def INSTMGR_GetStatusRpc(self):
        return 963
        
class SerIntrf(object):
    """
    Serial interface, the Picarro software talks over a serial port with
    the CoWS.
    Replacement: Accepts the commands C7,C8, Ax,Tx,Wx,Px as described in the code.
    On C7 and C8 the interface answers. C8 returns the status of the CoWS:
        water_Temperature,ePTFE_Temperature,trans_Temperature,air_FlowRate,PID_loops_locked

    """
    def __init__(self,p,**kwargs):
        self.port = 'COM%d' % p
        self.kwargs = kwargs
        self.answer = None
        self.send_time = None
        self.answerdict = dict(
                               C7='CoWS', # Device name
                               C8=' '.join(['0.0'] * 6), # Status
                               A1=None, A0=None, # Turn on/off airflow control
                               T1=None,T0=None,  # Turn on/off T control
                               W1=None,W0=None, # Turn on/off pump
                               P0=None,P1=None,P2=None,P3=None, # Move to valve position
                               # 
                               )
    def sendString(self,s):
        """
        Receives as string from the Coordinator
        """
        # print self.port,'<-',s
        # Set answer from answerdict
        self.send_time = time.time()
        if s.strip() in self.answerdict:
            self.answer = self.answerdict[s.strip()]
        else:
            self.answer= 'Unknown command: %s' % s
    def getLine(self):
        """
        Returns the answer of the interface and takes 4s after the send string (original behaviour)
        """
        time.sleep(max(0, 4-(time.time()-self.send_time)))
        return self.answer

# Variables used from Picarro software
ERROR_MSG=""
ERROR_STATE=""


# Helper variable to simulate scantime of picarro
last_meas_time = time.time()
# Scantime of the Picarro in seconds, real scantime is about 1.7s
scantime = 1.0

# Picarro functions to define measurement buffer, not used here
def setMeasBuffer(*args,**kwargs):
    pass
def clearMeasBuffer(*args,**kwargs):
    pass
    
fakepicarro = None
def measGetBufferFirst():
    """
    Returns dictionary of "measured" values. Real software returns the values given by setMeasBuffer
    If last query is before scantime, than return None (as in real application) 
    """
    return fakepicarro.get_result()
def fileDataFunc(data):
    """
    Function is given by picarro software and writes the data dictionary to a csv file
    Replaced by print out on screen
    """
    #print "fileDataFunc"
    pass
#     for k in sorted(data):
#         print '    %24s = %s' % (k,data[k])

# Dictionary for user defined parameters, copied from [UserEditableParams] section of .ini file
ParamDict = {
                "num_disp_params" : 0,
                0 : ("readytime", "Time in seconds needed to finish sample", "1080"),
                1 : ("switchtime", "Time in seconds before sample time, when the source may be switched already:", "180"),
                2 : ("averaging_Time" , "Time Duration for Averaging and Reporting Isotope Data in Seconds", "120"),
                3 : ("warmup_Time" , "Warmup delay in min, 0 for no warmup, 15 min for warmup", "15"),
                4 : ("warmup_Source", "Inlet for Water Source for System Warmup (15 Minutes): Select 1-4", "4"),
                5 : ("total_duration", "Total length of time for operation in Minutes: Select 0 for indefinite", "0"),
                6 : ("verbose", "Frequent output Y/N", "Y"),
                }
# Somewhere in the picarro software, the [UserEditableParams] section is stored as a dictionary
# of name,value pairs. This line converts the copied section above into the needed format
editParamDict = dict((item[0],item[-1]) for item in ParamDict.values() if type(item) is tuple)
# The GUI object of the picarro software seems to manage the graphic user interface. In the
# .ini it is only used to show warnings. The definition used here has the same behaviour as the
# GUI object

class GUI(object):
    @classmethod
    def popWarning(cls,msg):
        sys.stderr.write(msg + '\n')

# Create a coordinator .ini based on this script:
UEditParamStr = '\n        '.join('{} = "{}","{}","{}"'
                                  .format(k, *v) for k,v in ParamDict.items()
                                  if k in range(0,100))
chapters = open('CWS_Coordinator.py').read().split(splitsymbol)[1::2]
chapters[0]=chapters[0].replace('{editParams}',UEditParamStr)
chapters[-1]=chapters[-1].replace('#"""','"""')
text = '\n'.join(s[8:] for s in '\n'.join(chapters).split('\n'))
open('CWS_Coordinator_pk.ini', 'w').write(text)

# Load fake picarro
sys.path.append('..')
from proxies.picarro import FakePicarro

# The NEXT variable is used by the coordinator to know which section of the .ini is used next.
# The initial section is as given

NEXT = "StateSetupCoWS"

# Start a loop until StateDone is processed and NEXT is set to None
while NEXT:
    # Print out section to be processed from the .ini file
    logFunc("*" * 50 +  "\n" +  NEXT + "\n" + "*" * 50 + "\n")
    
    if NEXT=="StateSetupCoWS":
        """
#@-     
        [StateSetupCoWS]
        action = """
        logFunc("Loading modules...\n")
        import sys
        if 'splitsymbol' not in globals():
            sys.path.append("c:/python27/Lib/site-packages")

        from ilrcws.cwscommunicator import CoWSChecker, CoWSCommunicator

        logFunc("Searching COM ports for Continuous Water Sampler...\n")
        CoWS = None
        CoWSFound = False
        for p in range(2,100):
            if CoWS:
                CoWS.close()
                CoWS = None
            try:
                CoWS = SerIntrf(p, timeout=250, xonxoff=0)
                sleep(3)
            except:
                continue
            try:
                logFunc("Talking to COM%d...\n"%(p+1))
                CoWS.sendString("C7")
                status = CoWS.getLine()
                logFunc(status)
                if "CoWS" in status:
                    logFunc("CoWS found at COM%d...\n"%(p+1))
                    CoWSFound = True
                    break
            except:
                pass
                
        
        if not CoWSFound:
            logFunc("Continuous Water Sampler not found.\n")
            if CoWS:
                CoWS.close()
                CoWS = None
            GUI.popWarning("Continuous Water Sampler not found", "CoWS not found")
            raise Exception("CoWS not found")
        else:
            # Turn on Temperature Control
            CoWS.sendString("T1")
        
            # Turn on Air Flow Control
            CoWS.sendString("A1")
            # Turn on Water Pump
            CoWS.sendString("W1")
        
        NEXT = "StateSetup"
#@-
    elif NEXT=="StateSetup":# []
#@-     
        """
        [StateSetup]
        action = """

        # duration_Calibration = float(editParamDict["duration_Calibration"])*60.0
        averaging_Time = float(editParamDict["averaging_Time"])
        warmup_Time = int(editParamDict["warmup_Time"])
        warmup_Source = int(editParamDict["warmup_Source"])
        total_duration = float(editParamDict["total_duration"])*60.0
        concNameList = ["Delta_18_16", "Delta_D_H", "H2O", "CH4", "baseline_shift", "baseline_curvature", "slope_shift", "residuals"]
#@-
        fakepicarro = FakePicarro(concNameList,scantime,float(editParamDict['readytime']) * 0.5)
#@-
        setMeasBuffer("analyze_iH2O7200", concNameList, 2*averaging_Time)
        clearMeasBuffer()
        
        logFunc("Create checker\n")
        checker = CoWSChecker(editParamDict,concNameList)
        logFunc("Create communicator\n")
        communicator = CoWSCommunicator(checker)
        communicator.start()
        try:
            import CoordinatorScripts
            INSTMGR = CoordinatorScripts.INSTMGR
            logFunc("Using real instrument status...\n")
        except:
            logFunc("Using fake instrument status...\n")
            INSTMGR = InstMgrFake()

        
        data_Buffer = {}
        data_Buffer_Int = {}
        calculated_Results = {}
        
        line_Count = 0
        currentport = 0


        def str_time(t=None, postfix=''):
            # Returns a string representation of the utc time.
            # t is a float as returned by time.time(). If t is None, time.time() is called
            return time.strftime('%Y/%m/%d %H:%M:%S', time.gmtime(t or time.time())) + postfix

        def log_time(msg, t=None):
            logFunc('%s: %s\n' % (str_time(t), msg))

        def prepare_CoWS_Data():
            # Sends the status string to the CoWS but does NOT wait for an answer (approx. 4s)
            # returns the actual time
            try:
                CoWS.sendString("C8")
            except:
                log_time('Could not send C8 to CoWS!')
            return time.time()

        def get_CoWS_Data():
            # Reads the status from the CoWS, it is mandatory that prepare_CoWS_Data has been called before
            try:
                status = CoWS.getLine()
                CoWS_Status = status.split()
            except:
                logFunc('CoWS had no data!')
            return CoWS_Status

        def report_Data(results, sample=''):
            calculated_Results["H2O"] = results["H2O"]
            calculated_Results["Delta_D_H"] = results["Delta_D_H"]
            calculated_Results["Delta_18_16"] = results["Delta_18_16"]
            calculated_Results["CH4"] = results["CH4"]
            calculated_Results["line_Num"] = line_Count
            calculated_Results["time"] = round(((time.time()-start_Time_from_begining)/60.0),2)
            calculated_Results["startLocal"] = results['date']
            calculated_Results["baseline_shift"] = results["baseline_shift"]
            calculated_Results["baseline_curvature"] = results["baseline_curvature"]
            calculated_Results["slope_shift"] = results["slope_shift"]
            calculated_Results["residuals"] = results["residuals"]

            calculated_Results["water_Temperature"] = results.get('Water_T', 0.0)
            calculated_Results["ePTFE_Temperature"] = results.get('ePTFE_T', 0.0)
            calculated_Results["trans_Temperature"] = results.get('trans_T', 0.0)
            calculated_Results["air_Temperature"] = results.get('trans_T', 0.0)
            calculated_Results["air_FlowRate"] = results.get('air_Flow', 0.0)
            calculated_Results["PID_loops_locked"] = results.get('PID_loops_locked', 0.0)

            calculated_Results["sample_Inlet_Port"] = currentport
            calculated_Results["sample_name"] = sample
            fileDataFunc(calculated_Results)

            return calculated_Results

        start_Time_from_begining = time.time()
        if warmup_Time > 0:
            NEXT = "StateWarmUp"
        else:
            NEXT = "StateSample"
#@-            
    elif NEXT=="StateWarmUp":
#@-
        """
        [StateWarmUp]
        action = """
        currentport = int(warmup_Source)

        Position = "P" + str(warmup_Source)
        log_time("CoWS inlet set to Position %d..." % currentport)
        CoWS.sendString(Position)
        start_Time = start_Time_from_begining
        loop_time = time.time()
        log_time("start time " )
        # Send status request to CoWS, retrieve later
        cows_time = prepare_CoWS_Data()
        # Get a first data set
        results = measGetBufferFirst()
        while not results:
            sleep(0.2)
            results = measGetBufferFirst()
        log_time("got result: %0.1f ppm" % results['H2O'])
        # retrieve CoWS data
        cows_data = get_CoWS_Data()
        # prepare new CoWS data
        cows_time = prepare_CoWS_Data()

        if checker.verbose():
            log_time('New CoWS Data, %d values' % len(cows_data))

        checker.setstatus(warmup_Source, INSTMGR.INSTMGR_GetStatusRpc())
        line_Count += 1
        report_Data(results)
        log_time("Start WARMUP for %s min" % warmup_Time)

        start_warmup_time = time.time()

        while (time.time() - start_warmup_time) < warmup_Time * 60:
            loop_time = time.time()
            results = measGetBufferFirst()
            while not results:
                sleep(0.2)
                results = measGetBufferFirst()
            # Read CoWS only every 5sec
            if time.time() - cows_time >= 5.0:
                cows_data = get_CoWS_Data()
                cows_time = prepare_CoWS_Data()
                if checker.verbose():
                    log_time('new CoWS data, %d values, %0.0fs remain for warm up'
                            % (len(cows_data), warmup_Time*60 - (time.time()-start_warmup_time)))

            # Update results with CoWS data
            results.update(dict((k, float(v)) for k, v in
                                zip('Water_T ePTFE_T trans_T air_T air_Flow PID_loops_locked'.split(),
                                    cows_data)))
            results['warmup'] = warmup_Time * 60 - (time.time() - start_warmup_time)
            checker.appendvalues(time.time(), results)
            line_Count += 1

            report_Data(results, 'WarmUp')
            if checker.stop():
                break
        # Read remaining data from CoWS
        cows_data = get_CoWS_Data()
        if checker.stop():
            NEXT = "StatePause"
        else:
            NEXT = "StateSample"
#@-
    elif NEXT=="StateSample":
#@-
        """
        [StateSample]
        action = """
        nextport = 0
        if 'cows_data' not in globals():
            cows_data = [0.0] * 6
        cows_time = prepare_CoWS_Data()
        while (not total_duration) or (time.time()-start_Time_from_begining)<total_duration:
            # checker.nextport evaluates the stored results so far,
            # and decides which port to use next
            start_Time = time.time()
            checker.setstatus(currentport, INSTMGR.INSTMGR_GetStatusRpc())
            nextport, sample = checker.nextport(currentport, log_time)
            if nextport != currentport: # Next port gave a new port to sample
                cows_data = get_CoWS_Data()
                currentport=nextport
                log_time("%s: CoWS inlet set to Position %r..." % (time.ctime(),currentport))
#@-
                import numpy.random
                if currentport in [1, 2, 3]:
                    fakepicarro.change({1:-90, 2:-150, 3:numpy.random.uniform(-90,-150)}[currentport])
#@-
                # Change valco position
                Position = "P{}".format(currentport)
                CoWS.sendString(Position)
                cows_time = prepare_CoWS_Data()
            elif nextport == 0:
                # Clear CoWS buffer
                log_time('leave StateSample')
                break
            else:
                pass
            results = measGetBufferFirst()
            while not results:
                sleep(0.2)
                results = measGetBufferFirst()

            # Read CoWS only every 5sec
            if time.time() - cows_time >= 5.0:
                cows_data = get_CoWS_Data()
                cows_time = prepare_CoWS_Data()
                if checker.verbose():
                    log_time('new CoWS data, %d values' % len(cows_data))
            results.update(dict((k, float(v)) for k, v in
                                zip('Water_T ePTFE_T trans_T air_T air_Flow PID_loops_locked'.split(),
                                    cows_data)))
            results['warmup'] = 0
            checker.appendvalues(time.time(), results)
            
            for variable in results:
                data_Buffer.setdefault(variable, []).append(results[variable])
        
            line_Count += 1
            report_Data(results, sample)

        # read remaining data from serial buffer
        cows_data = get_CoWS_Data()
        NEXT = "StatePause"
#@-
    elif NEXT == "StatePause":
#@-
        """
        
        
        [StatePause]
        action="""
        CoWS.sendString("T0")
        CoWS.sendString("W0")
        CoWS.sendString("A0")
        log_time('CoWS went to pause mode...')
        while True:
            time.sleep(1.0)
            if checker.resume():
                log_time('CoWS resumes, 15min for warm up')
                NEXT='StateSetupCoWS'
                break
            elif checker.stop():
                log_time('StatePause: Stopping CoWS')
                NEXT='StateDone'
                break
#@-
    elif NEXT=="StateDone":
#@-        
        """
        [StateDone]
        action="""
        CoWS.sendString("T0")
        CoWS.sendString("W0")
        CoWS.sendString("A0")
        log_time("Done!")
        NEXT=""
#@-
    elif NEXT=="StateError":
#@-            
        """
        
        
        [StateError]
        action="""
        log_time("Error %s in state %s" % (ERROR_MSG,ERROR_STATE))
        NEXT = "StateDone"
        #"""
