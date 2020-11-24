#!/usr/bin/python3
import sys
sys.path.append('.')


import asyncio

from trailer.devices.valvesystem import ValveSystem


async def showprogress(vs):
    while not vs.is_ready.is_set():
        await vs.readstatus()
        p = vs.progress()
        print('{:20}{:4.0%} {}'.format(vs.action, p, '*' * int(p*50)), end='\r')
        asyncio.sleep(0.1)
    print()
    
async def showwait(t):
    print('wait', t,'s',end='\r')
    for i in range(t):
        await asyncio.sleep(1.0)
        print('wait', t-i-1,'s',end='\r')
    print()

async def empty(vs):
    print('empty complete')
    await vs.emptycomplete(timeout=90)
    await vs.readstatus()
    print('target={tgtvol_kg}, current={actvol_kg}'.format(**vs.data))
    await showprogress(vs)
    
    
async def test(vs):
    
    #print('calibrate scale for 500ml')
    #await vs.calibratescale(0.5)

    print('flush 20s')
    await vs.flush(34,20)
    await showprogress(vs)
    await vs.reset()
    await showwait(1)

    print('fill 0.2l')
    await vs.fill(34,0.2)
    await showprogress(vs)
    print('is filled')
    await vs.reset()
    await showwait(5)

    print('empty 0.1l to fridge')
    await vs.empty(0.1, tofridge=True)
    await showprogress(vs)
    
    await vs.reset()
    await showwait(5)

    print('empty all to waste')
    await vs.empty(tofridge=False)
    await showprogress(vs)
    await vs.reset()
    
    print('empty complete')
    await vs.emptycomplete()
    await showprogress(vs)
    await vs.reset()
    
    print('ready')
  
if __name__ == '__main__':  
    #port = sys.argv[1]
    loop = asyncio.get_event_loop()
    loop.set_debug(1)
    vs   = ValveSystem('/dev/trailerAlphaValves')
    #vs.pcl.debug = True
    if 's' in sys.argv:
        loop.run_until_complete(vs.reset())
        exit()
    if 'e' in sys.argv:
        loop.run_until_complete(empty(vs))
        exit()
    elif 'cal' in sys.argv:
        try:
            currvol = float(sys.argv[sys.argv.index('cal') + 1])
            
        except:
            print('Usage: test/valvesystem.py cal 0.0')
        else:
            loop.run_until_complete(vs.calibratescale(currvol))
            print(open('preferences/scale.yaml').read())
    else:
        loop.run_until_complete(test(vs))

    # open(__file__,'a').write('# {} successful on {}\n'.format(' '.join(sys.argv),time.ctime()))
