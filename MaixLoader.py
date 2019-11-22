#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# MAIXLoader class for kflash.py

import serial
import gc
import time
import math
import binascii
import hashlib
import struct
import K210Isp as Isp

# This is all the same logging stuff from kflash.py.  There must be a
# better way.

BASH_TIPS = dict(NORMAL='\033[0m',BOLD='\033[1m',DIM='\033[2m',UNDERLINE='\033[4m',
                    DEFAULT='\033[0m', RED='\033[31m', YELLOW='\033[33m', GREEN='\033[32m',
                    BG_DEFAULT='\033[49m', BG_WHITE='\033[107m')

ERROR_MSG   = BASH_TIPS['RED']+BASH_TIPS['BOLD']+'[ERROR]'+BASH_TIPS['NORMAL']
WARN_MSG    = BASH_TIPS['YELLOW']+BASH_TIPS['BOLD']+'[WARN]'+BASH_TIPS['NORMAL']
INFO_MSG    = BASH_TIPS['GREEN']+BASH_TIPS['BOLD']+'[INFO]'+BASH_TIPS['NORMAL']

def log(*args, **kwargs):
    print(*args, **kwargs)

# Values for fragmenting flash firmware.

MAX_RETRY_TIMES = 10
ISP_FLASH_SECTOR_SIZE = 4096
ISP_FLASH_DATA_FRAME_SIZE = ISP_FLASH_SECTOR_SIZE*16

def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]

    
class MAIXLoader:

    class TimeoutError(Exception): pass

    def change_baudrate(self, baudrate):
        log(INFO_MSG,"Selected Baudrate: ", baudrate, BASH_TIPS['DEFAULT'])
        out = struct.pack('III', 0, 4, baudrate)
        crc32_checksum = struct.pack('I', binascii.crc32(out) & 0xFFFFFFFF)
        out = struct.pack('HH', 0xd6, 0x00) + crc32_checksum + out
        self.write(out)
        time.sleep(0.05)
        self._port.baudrate = baudrate
        if args.Board == "goE":
            if baudrate >= 4500000:
                # OPENEC super baudrate
                log(INFO_MSG, "Enable OPENEC super baudrate!!!",  BASH_TIPS['DEFAULT'])
                if baudrate == 4500000:
                    self._port.baudrate = 300
                if baudrate == 6000000:
                    self._port.baudrate = 250
                if baudrate == 7500000:
                    self._port.baudrate = 350

    def change_baudrate_stage0(self, baudrate):
        # Dangerous, here are dinosaur infested!!!!!
        # Don't touch this code unless you know what you are doing
        # Stage0 baudrate is fixed
        # Contributor: [@rgwan](https://github.com/rgwan)
        #              rgwan <dv.xw@qq.com>
        baudrate = 1500000
        if args.Board == "goE" or args.Board == "trainer":
            log(INFO_MSG,"Selected Stage0 Baudrate: ", baudrate, BASH_TIPS['DEFAULT'])
            # This is for openec, contained ft2232, goE and trainer
            log(INFO_MSG,"FT2232 mode", BASH_TIPS['DEFAULT'])
            baudrate_stage0 = int(baudrate * 38.6 / 38)
            out = struct.pack('III', 0, 4, baudrate_stage0)
            crc32_checksum = struct.pack('I', binascii.crc32(out) & 0xFFFFFFFF)
            out = struct.pack('HH', 0xc6, 0x00) + crc32_checksum + out
            self.write(out)
            time.sleep(0.05)
            self._port.baudrate = baudrate

            retry_count = 0
            while 1:
                retry_count = retry_count + 1
                if retry_count > 3:
                    raise Exception(' '.join((ERROR_MSG,'Fast mode failed, please use slow mode by add parameter ' + BASH_TIPS['GREEN'] + '--Slow', BASH_TIPS['DEFAULT'])))
                try:
                    self.greeting()
                    break
                except TimeoutError:
                    pass
        elif args.Board == "dan" or args.Board == "bit" or args.Board == "kd233":
            log(INFO_MSG,"CH340 mode", BASH_TIPS['DEFAULT'])
            # This is for CH340, contained dan, bit and kd233
            baudrate_stage0 = int(baudrate * 38.4 / 38)
            # CH340 can not use this method, test failed, take risks at your own risk
        else:
            # This is for unknown board
            log(WARN_MSG,"Unknown mode", BASH_TIPS['DEFAULT'])

    def __init__(self, port='/dev/ttyUSB1', baudrate=115200):
        # configure the serial connections (the parameters differs on the device you are connecting to)
        self._port = serial.Serial(
            port=port,
            baudrate=baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.1
        )
        log(INFO_MSG, "Default baudrate is", baudrate, ", later it may be changed to the value you set.",  BASH_TIPS['DEFAULT'])


    def reset_to_isp(self):

        def resetAndGreet():
            
            # This is a difficult thing to do in Python, since timing is
            # important.  So we build our message here before resetting
            # (hopefully Python doesn't wait until it uses 'buf' to
            # evaluate it!), and disable garbage collection.

            buf = Isp.Nop().format()
            gc.disable()

            self._port.reset_input_buffer()
            self._port.reset_output_buffer()

            # Release RESET and BOOT.

            self._port.dtr = False
            self._port.rts = False
            time.sleep(0.01)

            # Pull RESET down and keep 10ms.

            self._port.dtr = True
            self._port.rts = True
            time.sleep(0.1)

            # Release RESET, leaving IO_16 low to enter ISP mode.

            self._port.dtr = True
            self._port.rts = False

            # Now _immediately_ write a NOP message (greeting) to the ISP
            # port or else it will boot normally.  We need to do this
            # fast--we can't even wait for the time it takes Python to
            # build a message using the ISP message module.

            self.write(buf)
            self._port.flush()
            gc.enable()

            # Return the K210's response.

            time.sleep(0.1)
            return self.read()
        
        buf = b''
        while True:
            try:
                print('.', end='', flush=True)
                buf = resetAndGreet()
                if len(buf) > 0: break
            except TimeoutError: pass
        log('read', len(buf), 'bytes: ', buf)

    def reset_to_boot(self):

        # Pull RESET down and keep 10ms.

        self._port.dtr = False
        self._port.rts = True
        time.sleep(0.01)

        # Release RESET, leaving IO_16 high to boot from flash.

        self._port.dtr = False
        self._port.rts = False
        time.sleep(0.01)

    def write(self, packet):
        buf = (b'\xc0'
               + packet.replace(b'\xdb', b'\xdb\xdd').replace(b'\xc0', b'\xdb\xdc')
               + b'\xc0')
        # log('wrote', len(buf), 'bytes: ', binascii.hexlify(buf))
        return self._port.write(buf)

    def read(self):

        # Listen for a return packet to arrive within the serial
        # timeout.

        buf = self._port.read_until(b'\xc0');
        buf += self._port.read_until(b'\xc0')

        if len(buf) == 0: raise TimeoutError
        log("read", len(buf), "bytes: ", binascii.hexlify(buf))

        # Now translate any SLIP escape sequences and ditch the
        # start and stop tokens.  Bail if it looks wrong.

        if len(buf) < 2 or buf[0] != 0xc0 or buf[-1] != 0xc0:
            raise Exception('*** Short or missing SLIP delimiter(s)!')

        packet = buf[1:-1].replace(b'\xdb\xdc', b'\xc0').replace(b'\xdb\xdd', b'\xdb')
        return packet


 
    def flash_greeting(self):

        retry_count = 0
        while 1:
            self.write(Isp.FlashGreet().format())
            retry_count = retry_count + 1
            try:
                m = Isp.parseMessage(self.read())
                op, reason = m.op, m.reason
                
            except TimeoutError:
                if retry_count > MAX_RETRY_TIMES:
                    raise Exception(' '.join((ERROR_MSG,"Failed to Connect to K210's Stub",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Timeout Error, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue
            except:
                if retry_count > MAX_RETRY_TIMES: raise
                    # raise Exception(' '.join((ERROR_MSG,"Failed to Connect to K210's Stub",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Unexpected Error, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue
            if (op == Isp.FlashGreet.op and reason == Isp.err['Ok']):
                log(INFO_MSG,"Booted to flash mode successfully.",BASH_TIPS['DEFAULT'])
                self._port.flushInput()
                self._port.flushOutput()
                break
            else:
                if retry_count > MAX_RETRY_TIMES:
                    raise Exception(' '.join((ERROR_MSG,"Failed to Connect to K210's Stub",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Unexpected Return recevied, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue

    def boot(self, address=0x80000000):
        log(INFO_MSG,"Booting From " + hex(address),BASH_TIPS['DEFAULT'])
        self.write(Isp.MemBoot(address, 0).format())

    def recv_debug(self):
        try:
            m = Isp.parseMessage(self.read())
        except TimeoutError:
            return False
        op, reason, text = m.op, m.reason, b''
        if text:
            log('-' * 30)
            log(text)
            log('-' * 30)
        if reason not in (Isp.err['Default'], Isp.err['Ok']):
            log('Failed, retry, errcode=', hex(reason))
            return False
        return True

    def flash_recv_debug(self):
        try:
            m = Isp.parseMessage(self.read())
        except TimeoutError:
            return False
        op, reason, text = m.op, m.reason, b''
        if text:
            log('-' * 30)
            log(text)
            log('-' * 30)

        if reason != Isp.err['Ok']:
            log('Failed, retry')
            return False
        return True

    def init_flash(self, chip_type):

        chip_type = int(chip_type)
        log(INFO_MSG,"Selected Flash: ",("In-Chip", "On-Board")[chip_type],BASH_TIPS['DEFAULT'])
        buf = Isp.InitFlash(chip_type).format()
        
        retry_count = 0
        while 1:
            sent = self.write(buf)
            retry_count = retry_count + 1
            try:
                reply = Isp.parseMessage(self.read())
                op, reason = reply.op, reply.reason
            except TimeoutError:
                if retry_count > MAX_RETRY_TIMES:
                    raise Exception(' '.join((ERROR_MSG,"Failed to initialize flash",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Timeout Error, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue
            except:
                if retry_count > MAX_RETRY_TIMES: raise
                    # raise Exception(' '.join((ERROR_MSG,"Failed to initialize flash",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Unexpected Error, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue
            if op == Isp.InitFlashReply.op and reason == Isp.err['Ok']:
                log(INFO_MSG,"Initialized flash successfully.",BASH_TIPS['DEFAULT'])
                break
            else:
                if retry_count > MAX_RETRY_TIMES:
                    raise Exception(' '.join((ERROR_MSG,"Failed to initialize flash",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Unexcepted Return recevied, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue

    def flash_dataframe(self, data, address=0x80000000):
        
        DATAFRAME_SIZE = 1024
        data_chunks = chunks(data, DATAFRAME_SIZE)
        #log('[DEBUG] flash dataframe | data length:', len(data))
        total_chunk = math.ceil(len(data)/DATAFRAME_SIZE)

        time_start = time.time()
        for n, chunk in enumerate(data_chunks):
            while 1:
                log('[INFO] sending chunk', n, '@address', hex(address), 'chunklen', len(chunk))
                m = Isp.MemWrite(address, len(chunk), 0, chunk)
                sent = self.write(m.format())
                log('[INFO]', 'sent', sent, 'bytes', 'checksum', '{0:#x}'.format(m.crc))
                if self.recv_debug():
                    break

            address += len(chunk)
            time_delta = time.time() - time_start
            speed = ''
            if (time_delta > 1):
                speed = str(int((n + 1) * DATAFRAME_SIZE / 1024.0 / time_delta)) + ' KiB/s'
            # printProgressBar(n+1, total_chunk, prefix = 'Downloading ISP:', suffix = speed, length = columns - 35)
            log('Downloading ISP:', n+1, '/', total_chunk, ',', speed)

            
    def dump_to_flash(self, data, address=0):

        log('[DEBUG] Programming', len(data), 'bytes at {0:#x}'.format(address))
        m = Isp.FlashWrite(address, len(data), 0, data)
        sent = self.write(m.format())
        log('[INFO]', 'sent', sent, 'bytes', 'checksum', m.crc)

        retry_count = 0
        while True:
            time.sleep(1)
            try:
                m = Isp.parseMessage(self.read())
                if m.reason != Isp.err['Ok']: raise Exception('Error: ', m.reason)
            except TimeoutError:
                retry_count = retry_count + 1
                if retry_count > MAX_RETRY_TIMES: raise
                continue
            break




    def flash_erase(self):
        
        log('[DEBUG] erasing spi flash.')
        # self._port.write(b'\xc0\xd3\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xc0')
        self.write(Isp.FlashErase().format())

        retry_count = 0
        while 1:
            retry_count = retry_count + 1
            try:
                m = Isp.parseMessage(self.read())
                op, reason = m.op, m.reason
                
            except TimeoutError:
                if retry_count > MAX_RETRY_TIMES:
                    raise Exception(' '.join((ERROR_MSG,"Failed to erase flash.",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Timeout Error, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue
            except:
                if retry_count > MAX_RETRY_TIMES: raise
                    # raise Exception(' '.join((ERROR_MSG,"Failed to erase flash.",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Unexpected Error, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue
            if (op == Isp.FlashGreet.op and reason == Isp.err['Ok']):
                log(INFO_MSG,"Erased flash successfully!",BASH_TIPS['DEFAULT'])
                self._port.flushInput()
                self._port.flushOutput()
                break
            else:
                if retry_count > MAX_RETRY_TIMES:
                    raise Exception(' '.join((ERROR_MSG,"Failed to erase flash.",BASH_TIPS['DEFAULT'])))
                log(WARN_MSG,"Unexpected Return recevied, retrying...",BASH_TIPS['DEFAULT'])
                time.sleep(0.1)
                continue



    def install_flash_bootloader(self, data):
        # Download flash bootloader
        self.flash_dataframe(data, address=0x80000000)

    def load_elf_to_sram(self, f):
        try:
            from elftools.elf.elffile import ELFFile
            from elftools.elf.descriptions import describe_p_type
        except ImportError:
            raise Exception(' '.join((ERROR_MSG,'pyelftools must be installed, run '+BASH_TIPS['GREEN']+'`' + ('pip', 'pip3')[sys.version_info > (3, 0)] + ' install pyelftools`',BASH_TIPS['DEFAULT'])))

        elffile = ELFFile(f)
        if elffile['e_entry'] != 0x80000000:
            log(WARN_MSG,"ELF entry is 0x%x instead of 0x80000000" % (elffile['e_entry']), BASH_TIPS['DEFAULT'])

        for segment in elffile.iter_segments():
            t = describe_p_type(segment['p_type'])
            log(INFO_MSG, ("Program Header: Size: %d, Virtual Address: 0x%x, Type: %s" % (segment['p_filesz'], segment['p_vaddr'], t)), BASH_TIPS['DEFAULT'])
            if not (segment['p_vaddr'] & 0x80000000):
                continue
            if segment['p_filesz']==0 or segment['p_vaddr']==0:
                log("Skipped")
                continue
            self.flash_dataframe(segment.data(), segment['p_vaddr'])

    def flash_firmware(self, firmware_bin, aes_key = None, address_offset = 0, sha256Prefix = True, filename = ""):
        # type: (bytes, bytes, int, bool) -> None
        # Don't remove above code!

        log('[DEBUG] flash_firmware DEBUG: aeskey=', aes_key)

        if sha256Prefix == True:
            # Add header to the firmware
            # Format: SHA256(after)(32bytes) + AES_CIPHER_FLAG (1byte) + firmware_size(4bytes) + firmware_data
            aes_cipher_flag = b'\x01' if aes_key else b'\x00'

            # Encryption
            if aes_key:
                enc = AES_128_CBC(aes_key, iv=b'\x00'*16).encrypt
                padded = firmware_bin + b'\x00'*15 # zero pad
                firmware_bin = b''.join([enc(padded[i*16:i*16+16]) for i in range(len(padded)//16)])

            firmware_len = len(firmware_bin)
            data = aes_cipher_flag + struct.pack('I', firmware_len) + firmware_bin
            sha256_hash = hashlib.sha256(data).digest()
            firmware_with_header = data + sha256_hash
            total_chunk = math.ceil(len(firmware_with_header)/ISP_FLASH_DATA_FRAME_SIZE)
            data_chunks = chunks(firmware_with_header, ISP_FLASH_DATA_FRAME_SIZE)  # 4kiB for a sector, 16kiB for dataframe

        else:
            total_chunk = math.ceil(len(firmware_bin)/ISP_FLASH_DATA_FRAME_SIZE)
            data_chunks = chunks(firmware_bin, ISP_FLASH_DATA_FRAME_SIZE)

        time_start = time.time()
        for n, chunk in enumerate(data_chunks):
            chunk = chunk.ljust(ISP_FLASH_DATA_FRAME_SIZE, b'\x00')  # align by size of dataframe
            self.dump_to_flash(chunk, address= n * ISP_FLASH_DATA_FRAME_SIZE + address_offset)
            time_delta = time.time() - time_start
            speed = ''
            if (time_delta > 1):
                speed = str(int((n + 1) * ISP_FLASH_DATA_FRAME_SIZE / 1024.0 / time_delta)) + ' KiB/s'
            # printProgressBar(n+1, total_chunk, prefix = 'Programming BIN:', filename=filename, suffix = speed, length = columns - 35)
            log('Programming firmware:', n+1, '/', total_chunk, ',', speed)


