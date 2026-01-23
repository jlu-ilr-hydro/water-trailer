def h():
    print("""
    Interactive robot control.
    start as:
    ipython -i test/irobot.py

    This script environment helps you to test the robotaio API.
    It wraps the important coroutines as short named functions for easy use.
    as listed below. If you want to call coroutines not listed here, 
    you can use the i() function to call a coroutine as a function:
    i(m1.is_referenced())

    The robot is r, and the motors are m1,m2,m3

    Wrapped coroutines:
    ref(m) : reference motor m in 1,2,3
    g(m, p): motor m go to absolute position p in mm
    gr(m,p): motor m go relative distance p in mm
    do(m, cmd): run command cmd on motor m, eg. do(1,'ZY'). Multiple commands can
                be executed as do(1, 'ZY', 'p1')
    s() : print status of robot
    x() : Stops all motors
    h(): Show this help
    """)
import asyncio
import trailer.devices.robotaio as robot
from time import sleep

r = robot.Robot('/dev/trailerRobot')

def i(coro):
        loop=asyncio.get_event_loop()
        return loop.run_until_complete(coro)
def s():
    i(r.readstatus())
    for k,v in r.data.items():
        print(k,'  :  ',v)

def do(m, *cmd):
    i(r.motors[m-1].do(*cmd))

def ref(m):
    i(r.motors[m-1].reference())
    s()

def g(m, p):
    i(r.motors[m-1].goabs(p))
    s()

def x():
    print('STOP!')
    i(asyncio.gather(*[m.stop() for m in r.motors]))
    s()
    
m1,m2,m3 = r.motors
robot.debug = 2
i(r.open())
h()
