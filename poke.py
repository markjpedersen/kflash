#!/usr/bin/python3

# poke.py
#
# This is a program to poke at the MAIX loader device on a MAIX Bit or
# Dan board.
#

import time
import serial

def log(*args, **kwargs):
    print(*args, **kwargs)
    
def slip_reader(port):
    
    partial_packet = None
    in_escape = False

    # We need to listen until we get a full packet, closed by \xc0.
    
    while True:

        waiting = port.in_waiting
#        read_bytes = port.read(1 if waiting == 0 else waiting)
        read_bytes = port.read(port.in_waiting)
        if read_bytes == b'':
            raise Exception("Timed out waiting for packet %s"
                            % ("header" if partial_packet is None else "content"))

        log("read", len(read_bytes), "bytes: ", str(read_bytes))
        
        for b in read_bytes:

            if type(b) is int:
                b = bytes([b])  # python 2/3 compat

            if partial_packet is None:  # waiting for packet header
                if b == b'\xc0':
                    partial_packet = b""
                else:
                    raise Exception('Invalid head of packet (%r)' % b)
            elif in_escape:  # part-way through escape sequence
                in_escape = False
                if b == b'\xdc':
                    partial_packet += b'\xc0'
                elif b == b'\xdd':
                    partial_packet += b'\xdb'
                else:
                    raise Exception('Invalid SLIP escape (%r%r)' % (b'\xdb', b))
            elif b == b'\xdb':  # start of escape sequence
                in_escape = True
            elif b == b'\xc0':  # end of packet
                yield partial_packet
                partial_packet = None
            else:  # normal byte in packet
                partial_packet += b


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
            timeout=0.1)
        
        log("Default baudrate is", baudrate)

        self._port.isOpen()
#        self.readPacket = slip_reader(self._port)

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

        self._port.setDTR (False)
        self._port.setRTS (False)
        time.sleep(0.1)

        # Pull reset down and keep 10ms
        self._port.setDTR (False)
        self._port.setRTS (True)
        time.sleep(0.1)

        # Pull IO16 to low and release reset
        self._port.setRTS (False)
        self._port.setDTR (False)
        time.sleep(0.1)

    def read(self):
        return next(slip_reader(self._port))
        
    def greeting(self):
        self._port.write(b'\xc0\xc2\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc0')
        time.sleep(0.1)
        text = self.read()
        log('MAIX returned: ', str(text))



l = MAIXLoader('/dev/ttyUSB0', baudrate=115200)

l.reset_to_isp_dan()
l.greeting()
l.reset_to_boot_dan()

