#!/usr/bin/python3
'''
Checks the flush time needed for the throughflow measurements

Setup needed: 
Two water source, one salted (for conductivity) at two valves
A csv file with ysi measurements is created (~/trailer/ysitest.csv) 
with lines for every second

Created on 04.05.2016

@author: kraft-p
'''
import sys
import time
sys.path.append('.')

import asyncio
from trailer.devices import valvesystem, ysi600r, ioalpha, tribox
from trailer.setup import address

async def createdev():
    a_io = await ioalpha.create(address.alphaIO)
    ysirelay = a_io.makerelay(1)
    T = asyncio.gather(valvesystem.create(address.alphaValves,empty=False),
                       ysi600r.create(address.ysi600r, ysirelay, stayopen=True),
                       return_exceptions=True)
    vs, ysi = await T
    ysi.integrationtime = 20
    a_io.addscale(1,'rainfill1',80)
    a_io.addscale(2,'rainfill2',80)
    return a_io, vs, ysi

async def test(valve1, valve2, changetime=600, usetribox=False):

    a_io, vs, ysi = await createdev()
    #with open('ysitest.csv','w') as fout:
    fout = sys.stdout
    try:
        fout.write('round,seconds_since_change,valve,conductivity, temp, \n')
        round = 0
        valves = valve1,valve2
        try:
            while True:
                await vs.reset()
                round += 1
                active_valve = valves[round % 2]
                print('-'*50)
                print('{} - flush from {} for {}'.format(round, active_valve,changetime))
                print('ctrl + C stops experiment')
                print('-'*50)
                await vs.flush(active_valve,changetime)
                tstart=time.time()
                while time.time()-tstart < changetime:
                    T = asyncio.gather(ysi.measure(),vs.readstatus(), a_io.readstatus())
                    res = await T
                    fout.write('{r},{t:5.1f},{v:2},{ysiConductivity:6.1f},{ysiT:6.1f},{ysipH:6.1f}\n'
                               .format(r=round,t=time.time()-tstart,v=active_valve,**res[0]))
                    fout.flush()
                    
        except KeyboardInterrupt:
            pass
        finally:
            await asyncio.gather(ysi.close(),vs.reset())
    finally:
        pass

if __name__ == '__main__':
    try:
        v1, v2, changetime = sys.argv[1:4]
        v1 = int(v1)
        v2 = int(v2)
        changetime = int(changetime)
    except:
        print('Usage: \n  test/throughflowtiming.py [valve1] [valve2] [changetime in s]')
        print('eg for change between valve 33 and 34 every 5 min:')
        print('  test/throughflowtiming.py 33 34 300')
        exit()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test(v1,v2,changetime,'t' in sys.argv))
