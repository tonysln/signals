import ctypes
import wave
import struct
import math


class Decoder():
    def __init__(self, f, iformat, encoding, mode, samp_rate=44100):
        self.file = f
        self.sr = samp_rate
        self.encoding = encoding
        self.mode = mode
        self.wav_samples = []

        self.load_libfft()


    def load_libfft(self):
        lib = ctypes.CDLL('../libfft.so')
        lib.fft.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.fft.restype = None
        lib.ifft.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.ifft.restype = None
        lib.dct.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.dct.restype = None
        lib.hann.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.hann.restype = None
        lib.filter.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.filter.restype = None
        lib.mag_power.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.mag_power.restype = None
        self.lib = lib


    def read_wav(self, in_path, chunk_size=4096):
        print('[.] Reading WAV samples...')
        self.wav_samples = []

        with wave.open(in_path, 'r') as f:
            sr_ = int(f.getframerate())
            flen = int(f.getnframes())
            ch = int(f.getnchannels())
            b = int(f.getsampwidth())

            i = 0
            while i < flen:
                n = min(chunk_size, flen-i)
                raw = f.readframes(n)
                self.wav_samples.extend(struct.unpack("<" + "h"*n, raw))

                # print(f'read={n}, i={i}/{flen-i}')
                i += n

            # print(f'final i={i}/{flen}')


    def process_wav_samples(self, N=1024, hop=256):
        print('[.] Processing WAV samples...')

        DoubleArray = ctypes.c_double * N
        hann = DoubleArray(*[0.0]*N)
        self.lib.hann(hann, N)

        slen = len(self.wav_samples)
        i = 0
        while i < slen:
            n = min(N, slen-i)

            slce = self.wav_samples[i:i+n]
            while len(slce) < N:
                slce.append(0.0)

            vals = DoubleArray(*slce)
            self.lib.filter(vals, hann, N)
            self.lib.dct(vals, N)

            mag = DoubleArray(*[0.0]*N)
            power = DoubleArray(*[0.0]*N)
            self.lib.mag_power(vals, mag, power, N)

            # print(f'win={n}, i={i}/{slen}')
            i += n

        # print(f'final i={i}/{slen}')


    def __del__(self):
        self.file.close()
