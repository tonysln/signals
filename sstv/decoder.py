import ctypes
import wave
import struct
import math
from encoder import *


class Decoder():
    modes = {
        44: (MartinEncoder, 'M1'),
        40: (MartinEncoder, 'M2'),
        36: (MartinEncoder, 'M3'),
        32: (MartinEncoder, 'M4'),
        60: (ScottieEncoder, 'S1'),
        56: (ScottieEncoder, 'S2'),
        52: (ScottieEncoder, 'S3'),
        48: (ScottieEncoder, 'S4'),
        76: (ScottieEncoder, 'DX'),
        51: (WrasseEncoder, 'SC2-30'),
        59: (WrasseEncoder, 'SC2-60'),
        63: (WrasseEncoder, 'SC2-120'),
        55: (WrasseEncoder, 'SC2-180'),
        113: (PasokonEncoder, 'P3'),
        114: (PasokonEncoder, 'P5'),
        115: (PasokonEncoder, 'P7'),
        93: (PDEncoder, 'PD50'),
        99: (PDEncoder, 'PD90'),
        95: (PDEncoder, 'PD120'),
        98: (PDEncoder, 'PD160'),
        96: (PDEncoder, 'PD180'),
        97: (PDEncoder, 'PD240'),
        94: (PDEncoder, 'PD290'),
        8: (RobotEncoder, '36'),
        12: (RobotEncoder, '72'),
        85: (FAXEncoder, 'FAX480')
    }

    def __init__(self, f, iformat, encoding, mode, samp_rate=44100):
        self.file = f
        self.sr = samp_rate
        self.encoding = encoding
        self.mode = mode
        self.pcm_samples = []

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
        self.pcm_samples = []

        with wave.open(in_path, 'r') as f:
            sr_ = int(f.getframerate())
            flen = int(f.getnframes())
            ch = int(f.getnchannels())
            b = int(f.getsampwidth())

            i = 0
            while i < flen:
                n = min(chunk_size, flen-i)
                raw = f.readframes(n)
                self.pcm_samples.extend(struct.unpack("<" + "h"*n, raw))

                # print(f'read={n}, i={i}/{flen-i}')
                i += n

            # print(f'final i={i}/{flen}')
    

    def find_window_peak(self, fbins, win, N):
        # Select peak in current window
        b = [None, 1e-10, None]
        for j,m in enumerate(win):
            if m > b[1]:
                b = fbins[j],m,j

        nf,c = self.interpolate_mag(win, b[2], N)
        return nf,c


    def process_pcm_samples(self, N=1024, hop=512):
        print('[.] Processing PCM stream...')

        fbins = [j * self.sr / N for j in range(0, N//2)]

        DoubleArray = ctypes.c_double * N
        hann = DoubleArray(*[0.0]*N)
        self.lib.hann(hann, N)

        slen = len(self.pcm_samples)

        # TODO:
        # template idea but based on estimated number of samples for each section


        i = 0
        fmax = []
        while i < slen:
            n = min(N, slen-i)

            slce = self.pcm_samples[i:i+n]
            while len(slce) < N:
                slce.append(0.0)

            real = DoubleArray(*slce)
            imag = DoubleArray(*[0.0]*N) # TODO use the double realFFT

            self.lib.filter(real, hann, N)
            self.lib.fft(real, imag, N)

            mag = DoubleArray(*[0.0]*N)
            pwr = self.lib.fft_mag_pwr(real, imag, mag, N)

            self.lib.mag_log(mag, N)
            nf,c = self.find_window_peak(fbins, mag, N)
            fmax.append((i*1000/self.sr,nf))

            # print(f'win={n}, i={i}/{slen}')
            i += min(hop, slen-i)

        # print(f'final i={i}/{slen}')

        return fmax


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


    def parse_samples(self, fft_res):
        recording = []
        cur_t = 0.0
        start_t = 0.0
        prev_f = None
        for i,(ms,ff) in enumerate(fft_res):
            # print(ms, f)
            ff = int(round(ff, -2)) if i < 21 else ff
            cur_t += ms - start_t

            if ff == prev_f:
                pass
            elif i > 0:
                recording += [(prev_f,round(cur_t / 5.0, -1))]
                cur_t = 0.0
                start_t = ms

            prev_f = ff

        return recording


    def decode_header(self, has_vox):
        pass


    def decode_VIS(self, vis_raw):
        vis = 0
        for v in vis_raw[::-1]:
            pass
        
        parity = sum(vis_raw) % 2 == 0

        assert vis in self.modes

        return self.modes[vis]


    def decode_phasing_interval(self):
        pass


    def hz_to_rgb(self, freq):
        return max(0, min(255, int(round((freq-1500.0) / 3.1372549))))


    def decode_image(self, template, recording):
        i = 0
        j = 0
        vis = ''
        parity = None
        state = -2
        lines = []
        gbr = [[], [], []]
        while i < len(template) and j < len(recording):
            t_f,t_ms = template[i]
            r_f,r_ms = recording[j]

            if abs(t_ms-r_ms) < 21:
                if i > 11 and i < 19:
                    vis = ('1' if r_f == 1100 else '0') + vis
                elif i == 19:
                    parity = r_f == 1300
                elif i == 20:
                    print('VIS:', vis, int(vis, 2))
                    print('parity:', parity, (vis.count('1')%2 == 0) == parity)
                elif i > 21:
                    if t_f == 1200 or t_f == 1500:
                        state += 1

                    if state > 2:
                        state = -2
                        lines.append(gbr)
                        gbr = [[], [], []]
                    else:
                        color = self.hz_to_rgb(r_f)
                        gbr[state].append(int(color))

            i += 1
            j += 1

        return lines
 

    def __del__(self):
        self.file.close()
