#!/usr/bin/python3

# poke.py
#
# This is a program to poke at the MAIX loader device on a MAIX Bit or
# Dan board.
#

import gc
import time
import serial
import binascii
import K210Isp as Isp
from MaixLoader import MAIXLoader
    
def readSram():
    print('Read SRAM.')
    l.write(Isp.MemRead(0x80000005, 10, 0, b'').format())
    Isp.parseMessage(l.read()).print()

def initFlash():
    print('Greet Flash.')
    l.write(Isp.FlashGreet().format())
    Isp.parseMessage(l.read()).print()
    print('Init Flash.')
    l.write(Isp.InitFlash(1).format())
    Isp.parseMessage(l.read()).print()

def eraseFlash():
    initFlash()
    print('Erase Flash.')
    l.write(Isp.FlashErase().format())
    Isp.parseMessage(l.read()).print()
    
l = MAIXLoader('/dev/ttyUSB0', baudrate=115200)

l.reset_to_isp()

initFlash()

l.reset_to_boot()

