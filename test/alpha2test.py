#!/usr/bin/python3
import asyncio
import sys
import time

sys.path.append('.')

from trailer.devices.alpha2 import Alpha2, w, r, Alpha2Sync


def check_add():
    print('r.O(1,2) == r.O(1) + r.O(2)')
    print(r.O([1, 2]) == r.O(1) + r.O(2))

    print('w.O([1,2],1) == (w.O(1) + w.O(2))')
    print(w.O([1, 2], True) == w.O(1, True) + w.O(2, True))
    print(w.O([1, 2], True).render())


async def tests(alpha2):
    print('open', alpha2)
    await alpha2.open()
    print('Check device')
    print(await alpha2.test())
    print('Stop program')
    await alpha2.stopprogram()
    # Open O1
    print('Open O1:', await alpha2.do(w.O(1, 1)))
    # Read O1
    print('O1:', await alpha2.do(r.O(1)))
    # Read I2
    print('I2:', await alpha2.do(r.I(2)))
    print('AI1:', await alpha2.do(r.AI(1)))
    print('O1,I1', await alpha2.do(r.O(1) + r.I(2)))
    print('O1,A1,I1', await alpha2.do(r.O(1) + r.AI(1) + r.I(2)))

    print('Close O1:', await alpha2.do(w.O(1, 0)))
    print('O1,I1:', await alpha2.do(r.O(1) + r.I(1)))

    #for i in range(1, 10):
    #    print('Open O%i:' % i, await alpha2(w.O(i, 1)))
    #    await asyncio.sleep(1.0)
    #    print('Close O%i:' % i, await alpha2(w.O(i, 0)))

    # Run alpha2 program
    await alpha2.runprogram()
    # Stop alpha2 program


def testsync(alpha2):
    print('open', alpha2.com['port'])
    alpha2.open()
    # Stop alpha2 program
    alpha2.stopprogram()
    # Check device
    print(alpha2.test())
    # Open O1
    print('Open O1:', alpha2(w.O(1, 1)))
    # Read O1
    print('O1:', alpha2(r.O(1)))
    # Read I2
    print('I2:', alpha2(r.I([2, 2])))
    print('AI1:', alpha2(r.AI(1)))
    print('O1,I1', alpha2(r.O(1) + r.I(2)))
    print('O1,A1,I1', alpha2(r.O(1) + r.AI(1) + r.I(2)))

    print('Close O1:', alpha2(w.O(1, 0)))
    print('O1,I1:', alpha2(r.O(1) + r.I(1)))

    for i in range(1, 10):
        print('Open O%i:' % i, alpha2(w.O(i, 1)))
        time.sleep(1.0)
        print('Close O%i:' % i, alpha2(w.O(i, 0)))

    # print(alpha2(w.O(list(range(1, 10)), 0)))
    # Run alpha2 program
    alpha2.runprogram()


if __name__ == '__main__':
    # This example program checks basic functionality
    # of the alpha2 without the need for a program running on it
    #
    # Setup:
    # Connect some actor to Output 1
    # Connect a variable voltage to Input 1 (as analog input)
    # Connect 24V switch to Input 2 (as digital input)
    # Optional: Connect other outputs
    if len(sys.argv) < 2:
        check_add()
        exit()
    port = sys.argv[1]
    if 'sync' in sys.argv:
        alpha2 = Alpha2Sync(port)
        # alpha2.debug = True
        testsync(alpha2)
    else:
        loop = asyncio.get_event_loop()
        loop.set_debug(1)
        alpha2 = Alpha2(port)
        # alpha2.debug = True

        loop.run_until_complete(tests(alpha2))

    open(__file__, 'a').write('# {} successful on {}\n'.format(' '.join(sys.argv), time.ctime()))

# test/alpha2test.py /dev/ttyUSB1 successful on Wed Mar 30 16:34:07 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Wed Mar 30 16:36:24 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Wed Mar 30 16:37:33 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Wed Mar 30 16:39:12 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Thu Apr  7 11:17:44 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Thu Apr  7 11:23:02 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Thu Apr  7 11:45:54 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Mon Apr 11 17:12:44 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Tue Apr 12 16:48:16 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Sun Apr 17 15:09:42 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Thu May 12 11:13:23 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Thu May 12 17:19:35 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Thu May 12 17:19:54 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Thu May 12 17:21:07 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:07:34 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:07:59 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:08:04 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:08:34 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:08:37 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:08:40 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Wed Oct 19 14:08:44 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Wed Oct 19 14:09:39 2016
# test/alpha2test.py /dev/ttyUSB1 successful on Thu Oct 20 11:00:41 2016
# test/alpha2test.py /dev/ttyUSB0 successful on Thu Oct 20 11:01:21 2016
# test/alpha2test.py /dev/trailerAlphaIO successful on Fri Nov 18 14:14:26 2016
# test/alpha2test.py /dev/trailerAlphaIO successful on Tue Dec  6 10:27:40 2016
