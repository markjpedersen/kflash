#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import (division, print_function)

import sys
import time
import zlib
import copy
import string
import struct
import binascii
import argparse
import math
import zipfile, tempfile
import json
import re
import os
import IspProg
from IspAes import AES
from IspAes import AES_128_CBC
from MaixLoader import MAIXLoader

# Logging things.

BASH_TIPS = dict(NORMAL='\033[0m', BOLD='\033[1m', DIM='\033[2m', UNDERLINE='\033[4m',
                 DEFAULT='\033[0m', RED='\033[31m', YELLOW='\033[33m', GREEN='\033[32m',
                 BG_DEFAULT='\033[49m', BG_WHITE='\033[107m')

ERROR_MSG   = BASH_TIPS['RED']+BASH_TIPS['BOLD']+'[ERROR]'+BASH_TIPS['NORMAL']
WARN_MSG    = BASH_TIPS['YELLOW']+BASH_TIPS['BOLD']+'[WARN]'+BASH_TIPS['NORMAL']
INFO_MSG    = BASH_TIPS['GREEN']+BASH_TIPS['BOLD']+'[INFO]'+BASH_TIPS['NORMAL']

def log(*args, **kwargs):
    print(*args, **kwargs)

def logInfo(*args, **kwargs):
    log(INFO_MSG, *args, BASH_TIPS['DEFAULT'], **kwargs)

def logWarn(*args, **kwargs):
    log(WARN_MSG, *args, BASH_TIPS['DEFAULT'], **kwargs)

def logErr(*args, **kwargs):
    log(ERROR_MSG, *args, BASH_TIPS['DEFAULT'], **kwargs)

    
class KFlash:

    def __init__(self):
        self.loader = None

    def process(self, terminal=True, dev="", baudrate=1500000, board=None,
                sram = False, file="", callback=None, noansi=False,
                terminal_auto_size=False, terminal_size=(50, 1), slow_mode = False):
        
        VID_LIST_FOR_AUTO_LOOKUP = "(1A86)|(0403)|(067B)|(10C4)|(C251)|(0403)"
        #                            WCH    FTDI    PL     CL    DAP   OPENEC
        ISP_RECEIVE_TIMEOUT = 0.5



        try:
            from enum import Enum
        except ImportError:
            raise Exception(' '.join((ERROR_MSG,'enum34 must be installed, run '+BASH_TIPS['GREEN']+'`' + ('pip', 'pip3')[sys.version_info > (3, 0)] + ' install enum34`',BASH_TIPS['DEFAULT'])))
        try:
            import serial
            import serial.tools.list_ports
        except ImportError:
            raise Exception(' '.join((ERROR_MSG,'PySerial must be installed, run '+BASH_TIPS['GREEN']+'`' + ('pip', 'pip3')[sys.version_info > (3, 0)] + ' install pyserial`',BASH_TIPS['DEFAULT'])))

        class ProgramFileFormat(Enum):
            FMT_BINARY = 0
            FMT_ELF = 1
            FMT_KFPKG = 2

        ISP_PROG = zlib.decompress(binascii.unhexlify(IspProg.TEXT))

        # ...progress bar snipped ...
        
        def open_terminal(reset):
            control_signal = '0' if reset else '1'
            control_signal_b = not reset
            import serial.tools.miniterm
            # For using the terminal with MaixPy the 'filter' option must be set to 'direct'
            # because some control characters are emited
            sys.argv = [sys.argv[0], _port, '115200', '--dtr='+control_signal, '--rts='+control_signal,  '--filter=direct']
            serial.tools.miniterm.main(default_port=_port, default_baudrate=115200, default_dtr=control_signal_b, default_rts=control_signal_b)
            sys.exit(0)

        boards_choices = ["kd233", "dan", "bit", "bit_mic", "goE", "goD", "maixduino", "trainer"]
        if terminal:
            parser = argparse.ArgumentParser()
            parser.add_argument("-p", "--port", help="COM Port", default="DEFAULT")
            parser.add_argument("-f", "--flash", help="SPI Flash type, 0 for SPI3, 1 for SPI0", default=1)
            parser.add_argument("-b", "--baudrate", type=int, help="UART baudrate for uploading firmware", default=115200)
            parser.add_argument("-l", "--bootloader", help="Bootloader bin path", required=False, default=None)
            parser.add_argument("-k", "--key", help="AES key in hex, if you need encrypt your firmware.", required=False, default=None)
            parser.add_argument("-v", "--version", help="Print version.", action='version', version='0.8.3')
            parser.add_argument("--verbose", help="Increase output verbosity", default=False, action="store_true")
            parser.add_argument("-t", "--terminal", help="Start a terminal after finish (Python miniterm)", default=False, action="store_true")
            parser.add_argument("-n", "--noansi", help="Do not use ANSI colors, recommended in Windows CMD", default=False, action="store_true")
            parser.add_argument("-s", "--sram", help="Download firmware to SRAM and boot", default=False, action="store_true")
            parser.add_argument("-B", "--Board",required=False, type=str, help="Select dev board", choices=boards_choices)
            parser.add_argument("-S", "--Slow",required=False, help="Slow download mode", default=False)
            parser.add_argument("firmware", help="firmware bin path")
            args = parser.parse_args()
        else:
            args = argparse.Namespace()
            setattr(args, "port", "DEFAULT")
            setattr(args, "flash", 1)
            setattr(args, "baudrate", 115200)
            setattr(args, "bootloader", None)
            setattr(args, "key", None)
            setattr(args, "verbose", False)
            setattr(args, "terminal", False)
            setattr(args, "noansi", False)
            setattr(args, "sram", False)
            setattr(args, "Board", None)
            setattr(args, "Slow", False)

        # udpate args for none terminal call
        if not terminal:
            args.port = dev
            args.baudrate = baudrate
            args.noansi = noansi
            args.sram = sram
            args.Board = board
            args.firmware = file

        if args.Board == "maixduino" or args.Board == "bit_mic":
            args.Board = "goE"

        manually_set_the_board = False
        if args.Board:
            manually_set_the_board = True

        if args.port == "DEFAULT":
            if args.Board == "goE":
                list_port_info = list(serial.tools.list_ports.grep("0403")) #Take the second one
                if len(list_port_info) == 0:
                    raise Exception(' '.join((ERROR_MSG,"No vaild COM Port found in Auto Detect, Check Your Connection or Specify One by"+BASH_TIPS['GREEN']+'`--port/-p`',BASH_TIPS['DEFAULT'])))
                list_port_info.sort()
                if len(list_port_info) == 1:
                    _port = list_port_info[0].device
                elif len(list_port_info) > 1:
                    _port = list_port_info[1].device
                log(INFO_MSG,"COM Port Auto Detected, Selected ", _port, BASH_TIPS['DEFAULT'])
            elif args.Board == "trainer":
                list_port_info = list(serial.tools.list_ports.grep("0403")) #Take the first one
                if(len(list_port_info)==0):
                    raise Exception(' '.join((ERROR_MSG,"No vaild COM Port found in Auto Detect, Check Your Connection or Specify One by"+BASH_TIPS['GREEN']+'`--port/-p`',BASH_TIPS['DEFAULT'])))
                list_port_info.sort()
                _port = list_port_info[0].device
                log(INFO_MSG,"COM Port Auto Detected, Selected ", _port, BASH_TIPS['DEFAULT'])
            else:
                try:
                    list_port_info = next(serial.tools.list_ports.grep(VID_LIST_FOR_AUTO_LOOKUP)) #Take the first one within the list
                    _port = list_port_info.device
                    log(INFO_MSG,"COM Port Auto Detected, Selected ", _port, BASH_TIPS['DEFAULT'])
                except StopIteration:
                    raise Exception(' '.join((ERROR_MSG,"No vaild COM Port found in Auto Detect, Check Your Connection or Specify One by"+BASH_TIPS['GREEN']+'`--port/-p`',BASH_TIPS['DEFAULT'])))
        else:
            _port = args.port
            log(INFO_MSG,"COM Port Selected Manually: ", _port, BASH_TIPS['DEFAULT'])

        self.loader = MAIXLoader(port=_port, baudrate=115200)
        file_format = ProgramFileFormat.FMT_BINARY

        # 0. Check firmware
        try:
            firmware_bin = open(args.firmware, 'rb')
        except FileNotFoundError:
            raise Exception(' '.join((ERROR_MSG,'Unable to find the firmware at ', args.firmware, BASH_TIPS['DEFAULT'])))

        with open(args.firmware, 'rb') as f:
            file_header = f.read(4)
            #if file_header.startswith(bytes([0x50, 0x4B])):
            if file_header.startswith(b'\x50\x4B'):
                if ".kfpkg" != os.path.splitext(args.firmware)[1]:
                    log(INFO_MSG, 'Find a zip file, but not with ext .kfpkg:', args.firmware, BASH_TIPS['DEFAULT'])
                else:
                    file_format = ProgramFileFormat.FMT_KFPKG

            #if file_header.startswith(bytes([0x7F, 0x45, 0x4C, 0x46])):
            if file_header.startswith(b'\x7f\x45\x4c\x46'):
                file_format = ProgramFileFormat.FMT_ELF
                if args.sram:
                    log(INFO_MSG, 'Find an ELF file:', args.firmware, BASH_TIPS['DEFAULT'])
                else:
                    raise Exception(' '.join((ERROR_MSG, 'This is an ELF file and cannot be programmed to flash directly:', args.firmware, BASH_TIPS['DEFAULT'] , '\r\nPlease retry:', args.firmware + '.bin', BASH_TIPS['DEFAULT'])))

        #------------------------------------------------------------
        # 1. Greeting.
        #
        
        log(INFO_MSG,"Trying to Enter the ISP Mode...",BASH_TIPS['DEFAULT'])

        self.loader.reset_to_isp()


        # Don't remove this line
        # Dangerous, here are dinosaur infested!!!!!
        ISP_RECEIVE_TIMEOUT = 3

        log()
        log(INFO_MSG,"Greeting Message Detected, Start Downloading ISP",BASH_TIPS['DEFAULT'])

        # if manually_set_the_board and (not args.Slow):
        #     if (args.baudrate >= 1500000) or args.sram:
        #         self.loader.change_baudrate_stage0(args.baudrate)

        #------------------------------------------------------------
        # 2. Download bootloader into SRAM.
        #

        logInfo('Loading bootloader into SRAM...')
        
        if args.sram and False:
            if file_format == ProgramFileFormat.FMT_KFPKG:
                raise Exception(' '.join((ERROR_MSG, "Unable to load kfpkg to SRAM")))
            elif file_format == ProgramFileFormat.FMT_ELF:
                self.loader.load_elf_to_sram(firmware_bin)
            else:
                self.loader.install_flash_bootloader(firmware_bin.read())
        else:
            # install bootloader at 0x80000000
            isp_loader = open(args.bootloader, 'rb').read() if args.bootloader else ISP_PROG
            self.loader.install_flash_bootloader(isp_loader)

        #------------------------------------------------------------
        # 3. Boot the loader from SRAM to run it.
        #
        
        self.loader.boot()

        if args.sram and False:
            # Dangerous, here are dinosaur infested!!!!!
            # Don't touch this code unless you know what you are doing
            # self.loader._port.baudrate = args.baudrate
            log(INFO_MSG,"Boot user code from SRAM", BASH_TIPS['DEFAULT'])
            if(args.terminal == True):
                open_terminal(False)
            msg = "Burn SRAM OK"
            raise Exception(msg)

        # Dangerous, here are dinosaur infested!!!!!
        # Don't touch this code unless you know what you are doing
        self.loader._port.baudrate = 115200

        log(INFO_MSG,"Wait For 0.1 second for ISP to Boot", BASH_TIPS['DEFAULT'])

        time.sleep(0.1)

        self.loader.flash_greeting()

        # if args.baudrate != 115200:
        #     self.loader.change_baudrate(args.baudrate)
        #     log(INFO_MSG,"Baudrate changed, greeting with ISP again ... ", BASH_TIPS['DEFAULT'])
        #     self.loader.flash_greeting()

        self.loader.init_flash(args.flash)


        #------------------------------------------------------------
        # 4. Download the firmware to flash, through the bootloader.
        #
        
        if file_format == ProgramFileFormat.FMT_KFPKG:
            log(INFO_MSG,"Extracting KFPKG ... ", BASH_TIPS['DEFAULT'])
            firmware_bin.close()
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    with zipfile.ZipFile(args.firmware) as zf:
                        zf.extractall(tmpdir)
                except zipfile.BadZipFile:
                    raise Exception(' '.join((ERROR_MSG,'Unable to Decompress the kfpkg, your file might be corrupted.',BASH_TIPS['DEFAULT'])))

                fFlashList = open(os.path.join(tmpdir, 'flash-list.json'), "r")
                sFlashList = re.sub(r'"address": (.*),', r'"address": "\1",', fFlashList.read()) #Pack the Hex Number in json into str
                fFlashList.close()
                jsonFlashList = json.loads(sFlashList)
                for lBinFiles in jsonFlashList['files']:
                    log(INFO_MSG,"Writing",lBinFiles['bin'],"into","0x%08x"%int(lBinFiles['address'], 0),BASH_TIPS['DEFAULT'])
                    with open(os.path.join(tmpdir, lBinFiles["bin"]), "rb") as firmware_bin:
                        self.loader.flash_firmware(firmware_bin.read(), None, int(lBinFiles['address'], 0), lBinFiles['sha256Prefix'], filename=lBinFiles['bin'])
        else:
            if args.key:
                aes_key = binascii.a2b_hex(args.key)
                if len(aes_key) != 16:
                    raise ValueError('AES key must by 16 bytes')

                self.loader.flash_firmware(firmware_bin.read(), aes_key=aes_key)
            else:
                self.loader.flash_firmware(firmware_bin.read())

        #------------------------------------------------------------
        # 3. Boot new firmware from flash!
        #

        self.loader.reset_to_boot()
        log(INFO_MSG,"Rebooting...", BASH_TIPS['DEFAULT'])
        try:
            self.loader._port.close()
        except Exception:
            pass

        if(args.terminal == True):
            open_terminal(True)



def main():
    kflash = KFlash()
    try:
        kflash.process()
    except Exception as e:
        if str(e) == "Burn SRAM OK":
            sys.exit(0)
        raise

if __name__ == '__main__':
    main()
