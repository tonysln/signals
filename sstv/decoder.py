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
        lib.fft_mag_pwr.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.fft_mag_pwr.restype = ctypes.c_double
        lib.mag_log.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.mag_log.restype = None
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


    def process_wav_samples(self, N=1024, hop=512):
        print('[.] Processing WAV samples...')

        fbins = [j * self.sr / N for j in range(0, N//2)]

        DoubleArray = ctypes.c_double * N
        hann = DoubleArray(*[0.0]*N)
        self.lib.hann(hann, N)

        slen = len(self.wav_samples)
        i = 0
        fmax = []
        while i < slen:
            n = min(N, slen-i)

            slce = self.wav_samples[i:i+n]
            while len(slce) < N:
                slce.append(0.0)

            real = DoubleArray(*slce)
            imag = DoubleArray(*[0.0]*N) # TODO use the double realFFT

            self.lib.filter(real, hann, N)
            self.lib.fft(real, imag, N)

            mag = DoubleArray(*[0.0]*N)
            pwr = self.lib.fft_mag_pwr(real, imag, mag, N)

            self.lib.mag_log(mag, N)

            # Select peak in current window
            b = [None, 1e-10, None]
            for j,m in enumerate(mag):
                if m > b[1]:
                    b = fbins[j],m,j

            nf,c = self.interpolate_mag(mag, b[2], N)
            fmax.append((i*1000/self.sr,nf))

            # print(f'win={n}, i={i}/{slen}')
            i += min(hop, slen-i)

        print(f'final i={i}/{slen}')
        print(len(fmax),fmax[:20])


    def interpolate_mag(self, mags, ind, N):
        # https://ccrma.stanford.edu/~jos/sasp/Quadratic_Interpolation_Spectral_Peaks.html
        
        nf = ind * self.sr / N
        c = mags[ind]

        if not (ind-1 > 0 and ind+1 < len(mags)):
            return nf,c
        
        p = mags[ind-1]
        n = mags[ind+1]

        # Consider only if local peak
        if c > p and c > n:
            d = 0.5*(p - n) / (p - 2*c + n)
            nf = (ind + d) * (self.sr / N)
            return nf,c - 0.25*(p - n) * d

        return nf,c
 

    def __del__(self):
        self.file.close()
