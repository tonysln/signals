import ctypes
import wave
import struct
import math
import statistics
from encoder import *
from ctypes import POINTER, c_double, c_int, c_int32
import logging
logger = logging.getLogger(__name__)


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

    def __init__(self, f, encoding, mode, samp_rate=44100):
        self.file = f
        self.sr = samp_rate
        self.encoding = encoding
        self.mode = mode
        self.pcm_samples = []
        self.slen = 0

        self.load_libfft()


    def load_libfft(self):
        lib = ctypes.CDLL('../lib/libfft.so')
        lib.goertzel.argtypes = [POINTER(c_double), c_double, c_double, c_int]
        lib.goertzel.restype = c_int32
        lib.fft.argtypes = [POINTER(c_double), POINTER(c_double), c_int]
        lib.fft.restype = None
        lib.ifft.argtypes = [POINTER(c_double), POINTER(c_double), c_int]
        lib.ifft.restype = None
        lib.dct.argtypes = [POINTER(c_double), c_int]
        lib.dct.restype = None
        lib.hann.argtypes = [POINTER(c_double), c_int]
        lib.hann.restype = None
        lib.filter.argtypes = [POINTER(c_double), POINTER(c_double), c_int]
        lib.filter.restype = None
        lib.fft_mag_pwr.argtypes = [POINTER(c_double), POINTER(c_double), POINTER(c_double), c_int]
        lib.fft_mag_pwr.restype = c_double
        lib.mag_log.argtypes = [POINTER(c_double), c_int]
        lib.mag_log.restype = None
        self.lib = lib


    def read_wav(self, in_path, chunk_size=4096):
        logger.info('Reading WAV samples...')
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
                i += n

        self.slen = len(self.pcm_samples)


    def find_window_peak(self, win, N):
        # Select peak in current window
        b = [1e-10, None]
        for j,m in enumerate(win):
            if m > b[0]:
                b = m,j

        if b[1]:
            return self.interpolate_mag(win, b[1], N)
        
        return -1,-1


    def process_image(self, start, N=64, hop=32):
        logger.info('Processing PCM stream...')

        DoubleArray = c_double * N
        hann = DoubleArray(*[0.0]*N)
        self.lib.hann(hann, N)
        nonsil = start
        prev_pwr = 0

        out = []
        i = start
        while i < self.slen:
            n = min(N, self.slen-i)

            slce = self.pcm_samples[i:i+n]
            while len(slce) < N:
                slce.append(0.0)

            real = DoubleArray(*slce)
            imag = DoubleArray(*[0.0]*N) # TODO use the double realFFT

            self.lib.filter(real, hann, N)
            self.lib.fft(real, imag, N)

            mag = DoubleArray(*[0.0]*N)
            pwr = self.lib.fft_mag_pwr(real, imag, mag, N)

            if not nonsil and pwr > prev_pwr and i > 0:
                nonsil = i
                print('starting at=', i)
            else:
                self.lib.mag_log(mag, N)
                nf,c = self.find_window_peak(mag, N)
                out.append((i,nf))

            prev_pwr = pwr
            i += min(hop, self.slen-i)

        return nonsil,out


    def find_nonsil(self, N=32, hop=16):
        # Cheaper way to find first non-silence samples

        DoubleArray = c_double * N
        hann = DoubleArray(*[0.0]*N)
        self.lib.hann(hann, N)

        i = 0
        while i < self.slen:
            n = min(N, self.slen-i)

            slce = self.pcm_samples[i:i+n]
            while len(slce) < N:
                slce.append(0.0)

            real = DoubleArray(*slce)
            self.lib.filter(real, hann, N)
            if self.lib.goertzel(real, 1900, self.sr, N):
                if i - N > 0:
                    i -= N
                return i

            i += min(hop, self.slen-i)

        return i


    def process_header(self, start, elen, N=64, hop=32):
        DoubleArray = c_double * N
        hann = DoubleArray(*[0.0]*N)
        self.lib.hann(hann, N)
        out = []

        i = start
        while i < start+elen:
            n = min(N, start+elen-i)

            slce = self.pcm_samples[i:i+n]
            while len(slce) < N:
                slce.append(0.0)

            real = DoubleArray(*slce)
            self.lib.filter(real, hann, N)
            freqs = [1100, 1200, 1300, 1500, 1900, 2300]
            g = [self.lib.goertzel(real, float(f), self.sr, N) for f in freqs]
            mg = max(g)
            m = freqs[g.index(mg)]
            out.append((i,m))

            i += min(hop, start+elen-i)

        return i,out



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


    def decode_VIS(self, start, freqs):
        step = int(round(self.sr*0.03))
        bits = []

        for i in range(start, start+step*10, step):
            bits.append(statistics.mode(freqs[i:i+step]))

        vis_raw = bits[1:8]
        parity_raw = bits[9]

        print(bits)

        vis = self.bin_to_dec_lsb(vis_raw)
        parity = [1,0][sum(vis_raw) % 2 == 0]

        if parity == parity_raw and vis in self.modes:
            return i,self.modes[vis]

        return i,bits


    def bin_to_dec_lsb(self, bits_list, n=0x40):
        res = 0
        for i,bit in enumerate(reversed(bits_list)):
            if bit:
                res |= (n >> i)
        return res


    def decode_phasing_interval(self, i):
        return i,None


    def hz_to_rgb(self, freq):
        return max(0, min(255, int(round((freq-1500.0) / 3.1372549))))


    def decode_image(self, encoder, start, freqs):
        pixels = []

        # Martin M1 example
        sync = int(round(self.sr * 4.862))
        t1 = int(round(self.sr * 0.572))
        pixel = int(round(self.sr * 0.4576))
        w = 320
        h = 256
        line = 3*(t1 + pixel*w)
        fline = sync + t1 + line
        full = h * line

        for i in range(0, full, fline):
            lp = []
            # TODO search around for sync+t1
            i += sync + t1

            for _ in range(3):
                for j in range(0, pixel*w, pixel):
                    lp.append(self.hz_to_rgb(freqs[j+i]))
                
                i += t1
            
            print(lp)
            pixels.append(lp)

        return pixels


    def decode_vox(self, start, freqs):
        bits = []
        step = int(round(self.sr*0.1))
        for i in range(start, start+step*8, step):
            bits.append(statistics.mode(freqs[i:i+step]))

        return i,bits


    def decode_header(self, start, freqs, is_fax):
        bits = []
        i = start

        if is_fax:
            step = int(round(self.sr*0.00205))
            
            for j in range(1220*2):
                bits.append(statistics.mode(freqs[i:i+step]))
                i += step
        else:
            step1 = int(round(self.sr*0.3))
            step2 = int(round(self.sr*0.01))

            for s in [step1, step2, step1]:
                bits.append(statistics.mode(freqs[i:i+s]))
                i += s

        return i,bits


    def __del__(self):
        self.file.close()
