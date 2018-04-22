#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" DJI Mavic Flight Controller Firmware Decryptor tool
"""

# Copyright (C) 2018  Jan Dumon <jan@crossbar.net>
# Copyright (C) 2018  Freek van Tienen <freek.v.tienen@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import re
import os
import hashlib
import binascii
import time
import argparse
from Crypto.Cipher import AES
from ctypes import *
from os.path import basename

encrypt_key = # TODO add key
encrypt_iv = # TODO add init vector

def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)

class EncHeader(LittleEndianStructure):
    _pack_ = 1
    _fields_ = [('target', c_ubyte),                #0
                ('unk0', c_uint),                   #1  Always 0x01000001
                ('version', c_ubyte * 4),           #5
                ('unk1', c_ubyte),                  #9  Always 0x01
                ('size', c_uint),                   #10
                ('unk2', c_uint),                   #14 Always 0x00000000
                ('time', c_uint),                   #18
                ('unk3', c_ubyte),                  #22 Always 0x04
                ('md5', c_ubyte * 16),              #23
                ('crc16', c_ushort)]                #39 end is 41

    def __init__(self):
        self.unk0 = 0x01000001
        self.unk1 = 0x01
        self.unk2 = 0x00000000
        self.unk3 = 0x04

    def dict_export(self):
        d = dict()
        for (varkey, vartype) in self._fields_:
            #if not varkey.startswith('unk'):
            d[varkey] = getattr(self, varkey)
        return d

    def __repr__(self):
        d = self.dict_export()
        from pprint import pformat
        return pformat(d, indent=4, width=1)

    def getTarget(self):
        tg_kind = self.target & 31
        tg_model = (self.target >> 5) & 7
        return (str(tg_kind).zfill(2) + str(tg_model).zfill(2))

    def getVersion(self):
        return ('v' + str(self.version[3]).zfill(2) + '.' + str(self.version[2]).zfill(2) + '.' + str(self.version[1]).zfill(2) + '.' + str(self.version[0]).zfill(2))

    def getTime(self):
        return (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.time)))

    def __str__(self):
        s =  'Target:     ' + self.getTarget() + '\n'
        s += 'Version:    ' + self.getVersion() + '\n'
        s += 'Time:       ' + self.getTime() + '\n'
        s += 'Size:       ' + str(self.size) + '\n'
        s += 'Data MD5:   ' + str(binascii.hexlify(self.md5)) + '\n'
        s += 'Header CRC: %04x' % self.crc16
        return s


def calc_checksum(packet, plength):
    crc = [0x0000, 0x1189, 0x2312, 0x329b, 0x4624, 0x57ad, 0x6536, 0x74bf, 0x8c48, 0x9dc1, 0xaf5a, 0xbed3, 0xca6c, 0xdbe5, 0xe97e, 0xf8f7,
           0x1081, 0x0108, 0x3393, 0x221a, 0x56a5, 0x472c, 0x75b7, 0x643e, 0x9cc9, 0x8d40, 0xbfdb, 0xae52, 0xdaed, 0xcb64, 0xf9ff, 0xe876,
           0x2102, 0x308b, 0x0210, 0x1399, 0x6726, 0x76af, 0x4434, 0x55bd, 0xad4a, 0xbcc3, 0x8e58, 0x9fd1, 0xeb6e, 0xfae7, 0xc87c, 0xd9f5,
           0x3183, 0x200a, 0x1291, 0x0318, 0x77a7, 0x662e, 0x54b5, 0x453c, 0xbdcb, 0xac42, 0x9ed9, 0x8f50, 0xfbef, 0xea66, 0xd8fd, 0xc974,
           0x4204, 0x538d, 0x6116, 0x709f, 0x0420, 0x15a9, 0x2732, 0x36bb, 0xce4c, 0xdfc5, 0xed5e, 0xfcd7, 0x8868, 0x99e1, 0xab7a, 0xbaf3,
           0x5285, 0x430c, 0x7197, 0x601e, 0x14a1, 0x0528, 0x37b3, 0x263a, 0xdecd, 0xcf44, 0xfddf, 0xec56, 0x98e9, 0x8960, 0xbbfb, 0xaa72,
           0x6306, 0x728f, 0x4014, 0x519d, 0x2522, 0x34ab, 0x0630, 0x17b9, 0xef4e, 0xfec7, 0xcc5c, 0xddd5, 0xa96a, 0xb8e3, 0x8a78, 0x9bf1,
           0x7387, 0x620e, 0x5095, 0x411c, 0x35a3, 0x242a, 0x16b1, 0x0738, 0xffcf, 0xee46, 0xdcdd, 0xcd54, 0xb9eb, 0xa862, 0x9af9, 0x8b70,
           0x8408, 0x9581, 0xa71a, 0xb693, 0xc22c, 0xd3a5, 0xe13e, 0xf0b7, 0x0840, 0x19c9, 0x2b52, 0x3adb, 0x4e64, 0x5fed, 0x6d76, 0x7cff,
           0x9489, 0x8500, 0xb79b, 0xa612, 0xd2ad, 0xc324, 0xf1bf, 0xe036, 0x18c1, 0x0948, 0x3bd3, 0x2a5a, 0x5ee5, 0x4f6c, 0x7df7, 0x6c7e,
           0xa50a, 0xb483, 0x8618, 0x9791, 0xe32e, 0xf2a7, 0xc03c, 0xd1b5, 0x2942, 0x38cb, 0x0a50, 0x1bd9, 0x6f66, 0x7eef, 0x4c74, 0x5dfd,
           0xb58b, 0xa402, 0x9699, 0x8710, 0xf3af, 0xe226, 0xd0bd, 0xc134, 0x39c3, 0x284a, 0x1ad1, 0x0b58, 0x7fe7, 0x6e6e, 0x5cf5, 0x4d7c,
           0xc60c, 0xd785, 0xe51e, 0xf497, 0x8028, 0x91a1, 0xa33a, 0xb2b3, 0x4a44, 0x5bcd, 0x6956, 0x78df, 0x0c60, 0x1de9, 0x2f72, 0x3efb,
           0xd68d, 0xc704, 0xf59f, 0xe416, 0x90a9, 0x8120, 0xb3bb, 0xa232, 0x5ac5, 0x4b4c, 0x79d7, 0x685e, 0x1ce1, 0x0d68, 0x3ff3, 0x2e7a,
           0xe70e, 0xf687, 0xc41c, 0xd595, 0xa12a, 0xb0a3, 0x8238, 0x93b1, 0x6b46, 0x7acf, 0x4854, 0x59dd, 0x2d62, 0x3ceb, 0x0e70, 0x1ff9,
           0xf78f, 0xe606, 0xd49d, 0xc514, 0xb1ab, 0xa022, 0x92b9, 0x8330, 0x7bc7, 0x6a4e, 0x58d5, 0x495c, 0x3de3, 0x2c6a, 0x1ef1, 0x0f78]

    v = 0x3692

    for i in range(0, plength):
        vv = v >> 8
        v = vv ^ crc[((packet[i] ^ v) & 0xFF)]
    return v

def unpack(args):
    header = EncHeader()
    if args.input.readinto(header) != sizeof(header):
        raise EOFError("Couldn't read image file header.")

    print(header)

    if (header.crc16 != calc_checksum(bytes(header), 39)):
        print('ERROR: CRC of the header doesn\'t match!')
        return -1

    data = args.input.read(((header.size + 255) // 256) * 256)

    # MD5 of the entire file
    md5_sum = hashlib.md5()
    md5_sum.update(header)
    md5_sum.update(data)
    md5_calc = md5_sum.digest()
    md5_read = args.input.read(16)

    if md5_calc == md5_read:
        print('File MD5 matches.')
    else:
        print('ERROR: File MD5 doesn\'t match!')
        return -1

    remaining = args.input.read()
    if len(remaining) != 0:
        print('ERROR: Trailing bytes!')
        return -1

    dec_buffer = bytes()
    for i in range((header.size + 255) // 256):
        enc_buffer = data[(i * 256):((i + 1) * 256)]
        cipher = AES.new(encrypt_key, AES.MODE_CBC, encrypt_iv)
        dec_buffer += cipher.decrypt(enc_buffer)

    md5_data = hashlib.md5()
    md5_data.update(dec_buffer)
    md5_calc = md5_data.digest()

    if md5_calc == bytes(header.md5):
        print('Data MD5 matches.')
    else:
        print('ERROR: Data MD5 doesn\'t match!')
        print('Data MD5:   ' + str(binascii.hexlify(md5_calc)))
        return -1

    if args.cmd == 'dec':
        if args.output == None:
            file_out = os.path.splitext(basename(args.input.name))[0] + '.decrypted.bin'
            args.output = open(file_out, "wb")
        else:
            file_out = args.output.name
        args.output.write(dec_buffer[:header.size])
        args.output.close()
        print("Decrypted file to " + file_out)

    return

def pack(args):
    header = EncHeader()

    data = args.input.read()

    # Calculate the md5
    header.md5 = (c_ubyte * 16)(*(hashlib.md5(data).digest()))
    header.size = len(data)

    # Target
    if args.target == '0305':
        header.target = 0xa3
    elif args.target == '0306':
        header.target = 0xc3
    else:
        print('ERROR: Unknown target: ' + args.target)
        return -1

    # Timestamp
    if args.time == None:
        header.time = int(time.time())
    else:
        if args.time.isdigit():
            t = int(args.time)
        else:
            t = time.strptime(args.time, '%Y-%m-%d %H:%M:%S')
            if t == None:
                print('ERROR: Wrong format for time: ' + args.time)
                return -1
            t = int(time.mktime(t))

        header.time = t

    ver = re.search('^v(\d+).(\d+).(\d+).(\d+)$', args.version)
    if ver == None:
        print('ERROR: Wrong version string format (vAA.BB.CC.DD): ' + args.version)
        return -1

    # Version
    header.version[3] = int(ver.group(1))
    header.version[2] = int(ver.group(2))
    header.version[1] = int(ver.group(3))
    header.version[0] = int(ver.group(4))

    # Calculate the header crc
    header.crc16 = calc_checksum(bytes(header), 39)

    print(header)

    # Encrypt the file
    enc_buffer = bytes()
    for i in range((int(len(data) + 255) // 256)):
        dec_buffer = data[(i * 256):((i + 1) * 256)]
        cipher = AES.new(encrypt_key, AES.MODE_CBC, encrypt_iv)
        enc_buffer += cipher.encrypt(dec_buffer)

    if args.output == None:
        file_out = os.path.splitext(basename(args.input.name))[0] + '.encrypted.bin'
        args.output = open(file_out, "wb")
    else:
        file_out = args.output.name

    args.output.write(header)
    args.output.write(enc_buffer)

    # MD5 of the entire file
    md5_sum = hashlib.md5()
    md5_sum.update(header)
    md5_sum.update(enc_buffer)
    args.output.write(md5_sum.digest())

    args.output.close()

    print("Encrypted file to " + file_out)

if __name__ == "__main__":
    # Parse command line options
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='cmd')
    parser_dec = subparsers.add_parser('dec', help='Decrypt')
    parser_dec.add_argument('-i', '--input', required=True, type=argparse.FileType('rb'), help='input file')
    parser_dec.add_argument('-o', '--output', type=argparse.FileType('wb'), help='output file')
    parser_enc = subparsers.add_parser('enc', help='Encrypt')
    parser_enc.add_argument('-i', '--input', required=True, type=argparse.FileType('rb'), help='input file')
    parser_enc.add_argument('-o', '--output', type=argparse.FileType('wb'), help='output file')
    parser_enc.add_argument('-T', '--time', help='Timestamp. If omitted the current time will be used. The ' + \
            'timestamp is either a number (seconds since epoch) or in the following format: ' + \
            '"year-month-day hour:min:sec"' )
    parser_enc.add_argument('-v', '--version', required=True, help='Version string in the form "vAA.BB.CC.DD"')
    parser_enc.add_argument('-t', '--target', required=True, help='Either 0305 or 0306')
    parser_inf = subparsers.add_parser('info', help='Info')
    parser_inf.add_argument('-i', '--input', required=True, type=argparse.FileType('rb'), help='input file')
    args = parser.parse_args()

    if (args.cmd == 'info') or (args.cmd == 'dec'):
        unpack(args)
    elif args.cmd == 'enc':
        pack(args)
    else:
        print("Unknown command: %s" % args.cmd)