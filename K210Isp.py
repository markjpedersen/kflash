#!/usr/bin/python3
# -*- coding: utf-8 -*-

# isp.py
#
# K210 ISP commands
#

from struct import Struct
import binascii
from enum import Enum

# The various "reasons" for a message, which is part of the header.

err = {'Default'    : 0x00,
       'Ok'         : 0xe0,
       'BadDataLen' : 0xe1,
       'BadCrc'     : 0xe2,
       'InvalidCmd' : 0xe3,
       'InitFailed' : 0xe4}

# Empty messages contain nothing but short headers.

class EmptyMessage:

    header = Struct('<BB')     # op, reason
    op = None
    reason = 0
    
    def __init__(self, reason=0):
        self.reason = reason
        
    def print(self): print(self.__dict__)
    
    def format(self):
        return self.header.pack(self.op, self.reason)

    @classmethod
    def parseHeader(cls, buf):
        op, reason = cls.header.unpack_from(buf)
        return op, reason
        
    @classmethod
    def parse(cls, buf):
        op, reason = cls.parseHeader(buf)
        return cls(reason)


# A regular message is an empty message with a CRC and a variable
# length body of binary data.

class Message(EmptyMessage):

    header = Struct('<HHI')     # op, reason, crc
    crc = 0
    body = b''
    
    def __init__(self, reason=0, buf=b''):
        self.body = buf
        self.crc = binascii.crc32(self.body) & 0xffffffff
        super().__init__(self.reason)
        
    def print(self): print(self.__dict__)
    
    def format(self):
        return self.header.pack(self.op, self.reason, self.crc) + self.body
    
    @classmethod
    def parseHeader(cls, buf):
        op, reason, crc = cls.header.unpack_from(buf)
        rest = buf[cls.header.size:]
        return op, reason, crc, rest
        
    @classmethod
    def parse(cls, buf):
        op, reason, crc, rest = cls.parseHeader(buf)
        return cls(reason, rest)


class Nop(EmptyMessage): op = 0xc2
class FlashGreet(EmptyMessage): op = 0xd2
class FlashErase(EmptyMessage): op = 0xd3
class MemReadReply(EmptyMessage): op = 0xc4
class MemWriteReply(EmptyMessage): op = 0xc3
class FlashWriteReply(EmptyMessage): op = 0xd4
class InitFlashReply(EmptyMessage): op = 0xd7

class Echo(Message): op = 0xc1

class MemRead(Message):
    op = 0xc4
    Body = Struct('<II')     # adrs, len
    def __init__(self, adrs, len, reason=0, dat=b''):
        self.adrs = adrs
        self.len = len
        self.reason = reason
        self.dat = dat
        super().__init__(self.reason, self.Body.pack(self.adrs, self.len) + self.dat)
    @classmethod
    def parse(cls, buf):
        op, reason, crc, rest = cls.parseHeader(buf)
        adrs, len = cls.Body.unpack_from(rest)
        return cls(adrs, len, reason, rest[cls.Body.size:])
    
class MemWrite(MemRead): op = 0xc3
class FlashWrite(MemRead): op = 0xd4

class MemBoot(Message):
    op = 0xc5
    Body = Struct('<II')        # adrs, len (zero)
    def __init__(self, adrs, reason=0):
        self.adrs = adrs
        self.reason = reason
        super().__init__(self.reason, self.Body.pack(self.adrs, 0x0))
    @classmethod
    def parse(cls, buf):
        op, reason, crc, rest = cls.parseHeader(buf)
        adrs, len = cls.Body.unpack_from(rest)
        return cls(adrs, reason)

class InitFlash(Message):
    op = 0xd7
    Body = Struct('<II')        # chiptype, 0
    def __init__(self, chip, reason=0):
        self.chip = chip
        super().__init__(self.reason, self.Body.pack(self.chip, 0x0))
    @classmethod
    def parse(cls, buf):
        op, reason, crc, rest = cls.parseHeader(buf)
        chip, _ = cls.Body.unpack_from(rest)
        return cls(chip, reason)
    
class SetBaud(Message):
    op = 0xd6
    Body = Struct('<III')       # 0, 4, baudrate
    def __init__(self, rate, reason=0):
        self.reason = reason
        self.rate = rate
        super().__init__(self.reason, self.Body.pack(0, 4, self.rate))
    @classmethod
    def parse(cls, buf):
        op, reason, crc, rest = cls.parseHeader(buf)
        _, _, rate = cls.Body.unpack_from(rest)
        return cls(rate, reason)

class SetBaudStage0(SetBaud): op = 0xc6
class DebugInfo(Message): op = 0xd1



# Parse a formatted message.

def parseMessage(buf):
    if len(buf) == 2:
        dispatch = {0xc2 : Nop,
                    0xc3 : MemWriteReply,
                    0xc4 : MemReadReply,
                    0xd2 : FlashGreet,
                    0xd3 : FlashErase,
                    0xd4 : FlashWriteReply,
                    0xd7 : InitFlashReply}
        op, reason = EmptyMessage.parseHeader(buf)
        return dispatch[op].parse(buf)
    else:
        dispatch = {0xc1 : Echo,
                    0xc2 : Nop,
                    0xc3 : MemWrite,
                    0xc4 : MemRead,
                    0xc5 : MemBoot,
                    0xd6 : SetBaud,
                    0xc6 : SetBaudStage0,
                    0xd1 : DebugInfo,
                    0xd2 : FlashGreet,
                    0xd3 : FlashErase,
                    0xd4 : FlashWrite,
                    0xd7 : InitFlash}
        op, reason, crc, rest = Message.parseHeader(buf)
        return dispatch[op].parse(buf)
