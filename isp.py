#!/usr/bin/python3
# -*- coding: utf-8 -*-

# isp.py
#
# K210 ISP commands
#

from struct import Struct
import binascii
from enum import Enum

class IspMessage:

    err = {0x00 : 'Default',
           0xe0 : 'Ok',
           0xe1 : 'BadDataLen',
           0xe2 : 'BadCrc',
           0xe3 : 'InvalidCmd'}
    
    Header = Struct('<HHI')     # op, zero, crc

    op = None
    crc = 0
    body = b''
    
    def __init__(self, buf=b''):
        self.body = buf
        self.crc = binascii.crc32(self.body) & 0xffffffff
        
    def print(self): print(self.__dict__)
    
    def format(self):
        return self.Header.pack(self.op, 0, self.crc) + self.body

    @classmethod
    def parseHeader(cls, buf):
        op, _, crc = cls.Header.unpack_from(buf)
        rest = buf[cls.Header.size:]
        return op, crc, rest
        
    @classmethod
    def parse(cls, buf):
        op, crc, rest = cls.parseHeader(buf)
        return cls(rest)


class IspNop(IspMessage): op = 0xc2
class IspEcho(IspNop): op = 0xc1
class IspFlashNop(IspNop): 0xd2

class IspMemRead(IspMessage):
    op = 0xc4
    Body = Struct('<II')     # adrs, len
    def __init__(self, adrs, len, dat):
        self.adrs = adrs
        self.len = len
        self.dat = dat
        super().__init__(self.Body.pack(self.adrs, self.len) + self.dat)
    @classmethod
    def parse(cls, buf):
        op, crc, rest = cls.parseHeader(buf)
        adrs, len = cls.Body.unpack_from(rest)
        return cls(adrs, len, rest[cls.Body.size:])
    
class IspMemWrite(IspMemRead): op = 0xc3

class IspMemBoot(IspMessage):
    op = 0xc5
    Body = Struct('<II')        # adrs, len (zero)
    def __init__(self, adrs):
        self.adrs = adrs
        super().__init__(self.Body.pack(self.adrs, 0x0))
    @classmethod
    def parse(cls, buf):
        op, crc, rest = cls.parseHeader(buf)
        adrs, len = cls.Body.unpack_from(rest)
        return cls(adrs)

class IspSetBaud(IspNop):
    op = 0xd6
    Body = Struct('<III')       # 0, 4, baudrate
    def __init__(self, rate):
        self.rate = rate
        super().__init__(self.Body.pack(0, 4, self.rate))
    @classmethod
    def parse(cls, buf):
        op, crc, rest = cls.parseHeader(buf)
        _, _, rate = cls.Body.unpack_from(rest)
        return cls(rate)

class IspSetBaudStage0(IspSetBaud): op = 0xc6
class IspDebugInfo(IspNop): op = 0xd1



# Parse a formatted message.

def parseIspMessage(buf):
    dispatch = {0xc1 : IspEcho,
                0xc2 : IspNop,
                0xc3 : IspMemWrite,
                0xc4 : IspMemRead,
                0xc5 : IspMemBoot,
                0xd6 : IspSetBaud,
                0xc6 : IspSetBaudStage0,
                0xd1 : IspDebugInfo}
    op, crc, rest = IspMessage.parseHeader(buf)
    return dispatch[op].parse(buf)
