#!/usr/bin/python3
import sys
import asyncio
from trailer.devices import wago_valvesystem as wago

# shortcut for lazy typing
F = asyncio.ensure_future


def inloop(coro):
    loop=asyncio.get_event_loop()
    return loop.run_until_complete(coro)


async def readstatus(wg, showall=False):
    status = await wg.readstatus()
    if showall:
        for k, v in status.items():
            print(k, v)
    else:
        print(('command: {command}, status: {status}, weight: {weight:0.2f}ml, elapsed: {elapsed:0.2f}s\n' +
                 'tgtweight: {tgtweight:0.1f}ml, valve: {valve}')
                 .format(**status))

        
async def wait(wg):
    await asyncio.sleep(0.1)
    await readstatus(wg)
    while not wg.is_ready.is_set():
        status = await wg.readstatus()
        print('{command!s:10}/{status!s:10} ({elapsed:6.2f}s, {weight:6.1f}ml) [{p:5.2%}]'
              .format(p=wg.progress(), **status), end='\r')
        await asyncio.sleep(0.02)
    print()
    print('wg.is_ready:', wg.is_ready.is_set())

async def flush(wg, valve=1,timeout=10.0, with_ysi=False):
    await readstatus(wg)
    await wg.flush(valve, timeout, with_ysi)
    await wait(wg)
    await readstatus(wg)

async def fill(wg, valve, tgtvol=100, timeout=10.0):
    await readstatus(wg)
    await wg.fill(int(valve), tgtvol, timeout=float(timeout))
    await wait(wg)
    await readstatus(wg)

async def empty(wg, tgtvol, timeout=10.0):
    await readstatus(wg)
    await wg.empty(tgtvol, timeout=float(timeout))
    await wait(wg)
    await readstatus(wg)

async def bempty(wg, valve, tgtvol, timeout=10.0):
    await readstatus(wg)
    await wg.bempty(valve, tgtvol, timeout)
    await wait(wg)
    await readstatus(wg)

async def calibrate(wg, tgtvol=0.0, timeout=60.0):
    await readstatus(wg)
    await wg.calibrate(tgtvol, timeout)
    await wait(wg)
    await wg.readstatus()
    print('Calibration offset: {calib_offset:0.4f}, gain: {calib_gain:0.4f} DU/ml'.format(**wg.data))
    
async def do(wg, *args):
    c = args[0]
    await wg.reset()
    if c == 'r':
        await readstatus(wg, True)
    elif c == 'c':
        await wg.clear_command()
        await readstatus(wg)
    elif c == 'u':
        await flush(wg, int(args[1]), float(args[2]))
    elif c == 'f':
        await fill(wg, int(args[1]), float(args[2]), float(args[3]))
    elif c == 'e':
        await empty(wg, float(args[1]), float(args[2]))
    elif c == 'be':
        await bempty(wg, int(args[1]), float(args[2]), float(args[3]))
    	
        
		
if __name__ == '__main__':
    wg = wago.WagoValvesystem('wago')
    # Check if it is not in interactive mode
    if not 'i' in sys.argv:
        # Check for missing cmdline args
        if len(sys.argv) < 2:
            print('Usage : test/wago.py [ruf] [valve] [timeout=10.0s]')
            print('         r: read status')
            print('         u: flush until timeout')
            print('         f: fill to 100 ml')
            print('         e: empty ysi until timeout')
            print('         be: empty resevoir until timeout')
            print('         i: use in intactve mode. Start as ipython3 -i test/wago.py i')
			            
        else:  # execute job
            inloop(do(wg, *sys.argv[1:]))

    else:  # Interactive mode

        # Open connection to wago valvesystem
        # Inform on interactive API to wago valvesystem
        def h():
            print("""
            Interactive communication with the WAGO valvesystem:
                t(10.0): set time out to 10s
                v(9): set valve to 10s
                r(): read status
                rr(): read status verbose
                x(): reset system
                u(): flush until timeout
                f(100.0): fill to 100ml
                e(5.0): empty to 5ml
                b(100.0): Back empty to 100ml
                ysi(): swith on ysi
                c(): calibrate offset
                c(200.0): calibrate gain for 200ml
            """)
        h()
        wago.debug = True
        def reload():
            inloop(wg.readstatus())
            return wg.timeout, wg.valve
        timeout, valve = reload()
        print('Current timeout: {:0.1f}s at valve {}'.format(timeout, valve))

        r = lambda: inloop(readstatus(wg))
        rr = lambda: inloop(readstatus(wg, True))
        x = lambda: inloop(wg.reset())
        u = lambda: inloop(flush(wg, valve, timeout=timeout))
        f = lambda tgtvol: inloop(fill(wg, valve, tgtvol, timeout))
        e = lambda tgtvol: inloop(empty(wg, tgtvol, timeout))
        b = lambda tgtvol: inloop(bempty(wg, valve, tgtvol, timeout))
        ysi = lambda : inloop(wg.start_ysi())
        def c(tgtvol=0):
            inloop(calibrate(wg, tgtvol, timeout))

        def t(tt):
            global timeout
            timeout = tt
            print('Current timeout: {:0.1f}s at valve {}'.format(timeout, valve))
        def v(vv):
            global valve
            valve = vv
            print('Current timeout: {:0.1f}s at valve {}'.format(timeout, valve))


