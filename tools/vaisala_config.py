#! /usr/bin/env python3
import sys
import serial
from trailer import address
def setting(port,time):
    """
    Updates the interval (I) and averaging time (A) of the sensors
    """
    def isint(s):
        try:
            i = int(s)
            return True
        except:
            return False
    s = serial.Serial(port, baudrate=9600, timeout=1)
    s.read(100)
    I=time
    # TODO: Read out actual time and execute commands in for loop
    cmd1 = ('2XWU,I=' + str(I) + '!').strip()
    cmd2 = ('2XTU,I=' + str(I) + '!').strip()
    cmd3 = ('2XWU,A=' + str(I) + '!').strip()
    cmd4 = ('2XRU,I=' + str(I) + '!').strip()        
    s.write((cmd1 + '\r\n').encode())
    response1 = s.readline()
    print(' -> ', response1.decode().strip())
    s.write((cmd2 + '\r\n').encode())
    response2 = s.readline()
    print(' -> ', response2.decode().strip())
    s.write((cmd3 + '\r\n').encode())
    response3 = s.readline()
    print(' -> ', response3.decode().strip())
    s.write((cmd4 + '\r\n').encode())
    response4 = s.readline()
    print(' -> ', response4.decode().strip())
   
def console(port):
    """
    Starts an interactive console for SDI12 commands
    """
    def isint(s):
        try:
            j = int(s)
            return True
        except:
            return False
    s = serial.Serial(port, baudrate=9600, timeout=1)
    s.read(100)
    while True:
        print('Enter SDI command in the form aX! to check the new setting')
        print('q to quit')
        cmd = input('Command:').strip()
        if cmd.lower().startswith('q'):
            break
        elif cmd.endswith('!'):
            s.write((cmd + '\r\n').encode())
            response = s.readline()
            print(' -> ', response.decode().strip())
        else:
            print('Command did not end with !')

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1].startswith('h'):
        print('Usage: test/vaisala_config.py [sc]')
        print('   s: update SDI12 setting on port  [time]')
        print('   c: opens a SDI12 console on port ')
    elif sys.argv[1] == 's':
        if len(sys.argv)<3:
            print('need to get a time')
        setting(address.sdi12, int(sys.argv[2]))
    elif sys.argv[1] == 'c':
        console(address.sdi12)
