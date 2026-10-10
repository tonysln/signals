#!/usr/bin/env python3

import sys
import ctypes
from ctypes import POINTER, c_double, c_int, c_void_p
import logging
logger = logging.getLogger(__name__)


class FSKEncoder():
    def __init__(self):
        self.phase = 0.0
        self.clock = 0.0
        self.last_sample = 0
        self.SR = samp_rate
        self.A = 32767
        self.file = f

        logger.info(f'Using sample rate {self.SR} Hz')

        self.baud = 1200
        self.mark_hz = 1200
        self.space_hz = 2200


    def encode(self):
        # TODO tone generation, framing
        pass



class FSKDecoder():
    def __init__(self):
        pass


    def load_libfft(self):
        lib = ctypes.CDLL('../lib/libfft.so')
        lib.goertzel_sums.argtypes = [c_void_p, c_int, c_double, c_double, POINTER(c_double)]
        lib.goertzel_sums.restype = None
        lib.goertzel.argtypes = [POINTER(c_double), c_int, c_double, c_double]
        lib.goertzel.restype = c_double
        self.lib = lib


    def decode(self):
        # TODO read samples, compare mark and space tone power per bit
        # (goertzel), bit timing, framing
        pass



if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(1)


    logger.info('Done.')
