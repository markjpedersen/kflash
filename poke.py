#!/usr/bin/python3

# poke.py
#
# This is a program to poke at the MAIX loader device on a MAIX Bit or
# Dan board.
#

import time
import serial
import binascii
from enum import Enum
import struct


def log(*args, **kwargs):
    print(*args, **kwargs)
    

class ISP:

    class Operation(Enum):
        ISP_ECHO = 0xC1
        ISP_NOP = 0xC2
        ISP_MEMORY_WRITE = 0xC3
        ISP_MEMORY_READ = 0xC4
        ISP_MEMORY_BOOT = 0xC5
        ISP_DEBUG_INFO = 0xD1
        ISP_CHANGE_BAUDRATE = 0xc6

    class Error(Enum):
        ISP_RET_DEFAULT = 0
        ISP_RET_OK = 0xE0
        ISP_RET_BAD_DATA_LEN = 0xE1
        ISP_RET_BAD_DATA_CHECKSUM = 0xE2
        ISP_RET_INVALID_COMMAND = 0xE3

    cmd = struct.Struct('<HHIII')
    DebugCmd = struct.pack('<HH', 0xd1, 0)
    
    @staticmethod
    def parse(data):

        # type: (bytes) -> (int, int, str)

        op = int(data[0])
        reason = int(data[1])
        text = ''

        try:
            if ISP.Operation(op) == ISP.Operation.ISP_DEBUG_INFO:
                text = data[2:].decode()
        except ValueError:
            KFlash.log('Warning: recv unknown op', op)

        return (op, reason, text)

class MAIXLoader:

    def __init__(self, port='/dev/ttyUSB1', baudrate=115200):

        # configure the serial connections (the parameters differs on
        # the device you are connecting to)

        self._port = serial.Serial(
            port=port,
            baudrate=baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1)
        
        log("Default baudrate is", baudrate)

    def reset_to_isp_dan(self):

        # Pull RESET and IO_16 down and keep 10ms.
        
        self._port.setDTR (True)
        self._port.setRTS (True)
        time.sleep(0.01)

        # Release RESET, leaving IO_16 low to enter ISP mode.
        
        self._port.setDTR (True)
        self._port.setRTS (False)
        time.sleep(0.01)

    def reset_to_boot_dan(self):

        # Pull RESET down and keep 10ms.
        
        self._port.setDTR (False)
        self._port.setRTS (True)
        time.sleep(0.01)

        # Release RESET, leaving IO_16 high to boot from flash.
        
        self._port.setDTR (False)
        self._port.setRTS (False)
        time.sleep(0.01)

    def write(self, packet):
        buf = b'\xc0' \
              + (packet.replace(b'\xdb', b'\xdb\xdd').replace(b'\xc0', b'\xdb\xdc')) \
              + b'\xc0'
        log('[WRITE]', binascii.hexlify(buf))
        return self._port.write(buf)

    def read(self):

        # First, listen for a packet start token, \xc0.  It needs to
        # arrive within a serial read timeout.  If it doesn't, or we get
        # anything else, throw an exception.

        buf = self._port.read(1)
        if buf != b'\xc0':
            raise Exception("SLIP read wrong start token: ", buf[0])

        # Listen until we get a full packet, terminated by \xc0.

        buf += self._port.read_until('\xff', self._port.in_waiting)
        log("read", len(buf), "bytes: ", str(buf))

        # Now translate any SLIP escape sequences and ditch the
        # start and stop tokens.

        packet = buf[1:-1].replace(b'\xdb\xdc', b'\xc0').replace(b'\xdb\xdd', b'\xdb')
        return packet

    def poke(self):

        # buf = ISP.cmd.pack(0xc2, 0, 0, 0, 0)
        adrs = 0x80000000
        n = 10
        crc = binascii.crc32(struct.pack('<II', adrs, n)) & 0xffffffff
        log('crc: ', hex(crc))
        buf = ISP.cmd.pack(0xc4, 0, crc, adrs, n)
        log('xmit buf: ', str(buf))
        self.write(buf)
        time.sleep(1)
        reply = self.read()
        log('MAIX returned: ', str(reply))
        op, reason, text = ISP.parse(reply)
        log('ISP response:', ISP.Operation(op).name,
            ISP.Error(reason).name, text)


l = MAIXLoader('/dev/ttyUSB0', baudrate=115200)

l.reset_to_isp_dan()
l.poke()
l.reset_to_boot_dan()

