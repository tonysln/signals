import math
import struct
import array
import wave
from functools import lru_cache


class Encoder():
    def __init__(self, f, wave=True, samp_rate=44100):
        self.phase = 0.0
        self.clock = 0.0
        self.last_sample = 0
        self.SR = samp_rate
        self.A = 32767
        self.file = f
        self.wav = wave

        print(f'[.] Using sample rate {self.SR} Hz')

        self.lum_max = 255
        self.lum_w_hz = 2300
        self.lum_b_hz = 1500

        self.intro_tone_hz = [1900,1500,1900,1500,2300,1500,2300,1500]
        self.intro_tone_ms = 100

        if self.wav:
            print('[.] Writing output as WAV')
            self.file.setparams((1, 2, self.SR, 0, 'NONE', 'Uncompressed'))
        else:
            print('[!] Writing output as raw PCM samples')


    def generate_tone(self, f_hz, t_ms):
        t_s = t_ms / 1000.0
        self.clock += t_s

        # Closest sample we should use without cutting
        end_sample = round(self.clock * self.SR)

        total_samples = end_sample - self.last_sample
        phase_inc = 2 * math.pi * f_hz / self.SR

        b = array.array('h', [0]*total_samples)
        i = 0
        while i < total_samples:
            sample = max(-self.A, min(self.A, int(self.A * math.sin(self.phase))))
            self.phase = (self.phase + phase_inc) % (2 * math.pi)
            b[i] = sample
            i += 1

        if not self.wav:
            self.file.write(b.tobytes())
        else:
            self.file.writeframes(b.tobytes())

        self.last_sample = end_sample


    def encode_image(self, data):
        print('[.] Encoding image data...')
        for y in range(self.enc['height']):
            w = self.enc['width']
            self.encode_line(data[y*w*3 : (y+1)*w*3])


    def generate_intro(self):
        print('[+] Generating VOX intro code...')
        for hz in self.intro_tone_hz:
            self.generate_tone(f_hz=hz, t_ms=self.intro_tone_ms)


    def generate_header(self):
        print('[.] Generating header...')
        self.generate_tone(f_hz=1900, t_ms=300)
        self.generate_tone(f_hz=1200, t_ms=10)
        self.generate_tone(f_hz=1900, t_ms=300)


    def generate_VIS(self):
        print('[.] Generating VIS code...')
        self.generate_tone(f_hz=1200, t_ms=30) # start bit

        vis_bits = self.dec_to_bin_lsb(self.enc['vis'])
        for bit in vis_bits: # LSB, 7 data
            hz = 1100 if bit else 1300
            self.generate_tone(f_hz=hz, t_ms=30)
        
        even_parity = sum(vis_bits) % 2 == 0
        hz = 1300 if even_parity else 1100
        self.generate_tone(f_hz=hz, t_ms=30) # parity bit
        self.generate_tone(f_hz=1200, t_ms=30) # stop bit


    @lru_cache(maxsize=4096)
    def rgb_to_y(self, R, G, B):
        return 16.0 + (0.003906 * ((65.738 * R) + (129.057 * G) + (25.064 * B)))

    @lru_cache(maxsize=4096)
    def rgb_to_ry(self, R, G, B):
        return 128.0 + (0.003906 * ((112.439 * R) + (-94.154 * G) + (-18.285 * B)))

    @lru_cache(maxsize=4096)
    def rgb_to_by(self, R, G, B):
        return 128.0 + (0.003906 * ((-37.945 * R) + (-74.494 * G) + (112.439 * B)))

    def dec_to_bin_lsb(self, val, n=7):
        return [(val >> i) & 1 for i in range(n)]


    def __del__(self):
        self.file.close()


class MartinEncoder(Encoder):
    opts = {
        'M1': {
            't_pixel': 0.4576,
            'vis': 44,
            'width': 320,
            'height': 256
        },
        'M2': {
            't_pixel': 0.2288,
            'vis': 40,
            'width': 320,
            'height': 256
        },
        'M3': {
            't_pixel': 0.4576,
            'vis': 36,
            'width': 320,
            'height': 128
        },
        'M4': {
            't_pixel': 0.2288,
            'vis': 32,
            'width': 320,
            'height': 128
        }
    }

    def __init__(self, f, wav, mode='M1', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using MartinEncoder with mode {mode}')
        self.sync_hz = 1200
        self.sync_ms = 4.862
        self.t1_hz = 1500
        self.t1_ms = 0.572


    def encode_line(self, line):
        self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)
        self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)

        for j in [1, 2, 0]: # GBR
            for i in range(0, self.enc['width']):
                # f_l = (line[i*3 + j] * (self.lum_w_hz - self.lum_b_hz)) / self.lum_max
                f_l = line[i*3 + j] * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+f_l, t_ms=self.enc['t_pixel'])

            self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)


class ScottieEncoder(Encoder):
    opts = {
        'S1': {
            't_pixel': 0.4320,
            'vis': 60,
            'width': 320,
            'height': 256
        },
        'S2': {
            't_pixel': 0.2752,
            'vis': 56,
            'width': 320,
            'height': 256
        },
        'S3': {
            't_pixel': 0.4320,
            'vis': 52,
            'width': 320,
            'height': 128
        },
        'S4': {
            't_pixel': 0.2752,
            'vis': 48,
            'width': 320,
            'height': 128
        },
        'DX': {
            't_pixel': 1.0800,
            'vis': 76,
            'width': 320,
            'height': 256
        }
    }

    def __init__(self, f, wav, mode='S1', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using ScottieEncoder with mode {mode}')
        self.first_line_done = False
        self.sync_hz = 1200
        self.sync_ms = 9
        self.t1_hz = 1500
        self.t1_ms = 1.5


    def encode_line(self, line):
        if not self.first_line_done:
            self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)
            self.first_line_done = True

        self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)

        for j in [1, 2, 0]: # GBR
            for i in range(0, self.enc['width']):
                # f_l = (line[i*3 + j] * (self.lum_w_hz- self.lum_b_hz)) / self.lum_max
                f_l = line[i*3 + j] * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+f_l, t_ms=self.enc['t_pixel'])

            if j == 2:
                self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)

            if j != 0:
                self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)


class WrasseEncoder(Encoder):
    opts = {
        'SC2-30': {
            't_pixel': 0.18125,
            'vis': 51,
            'width': 320,
            'height': 128
        },
        'SC2-60': {
            't_pixel': 0.18125,
            'vis': 59,
            'width': 320,
            'height': 256
        },
        'SC2-120': {
            't_pixel': 0.365625,
            'vis': 63,
            'width': 320,
            'height': 256
        },
        'SC2-180': {
            't_pixel': 0.734375,
            'vis': 55,
            'width': 320,
            'height': 256
        }
    }

    def __init__(self, f, wav, mode='SC2-180', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using WrasseEncoder with mode {mode}')
        self.sync_hz = 1200
        self.sync_ms = 5.5225
        self.t1_hz = 1500
        self.t1_ms = 0.5


    def encode_line(self, line):
        self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)
        self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)

        for j in [0, 1, 2]: # RGB
            for i in range(0, self.enc['width']):
                # f_l = (line[i*3 + j] * (self.lum_w_hz - self.lum_b_hz)) / self.lum_max
                f_l = line[i*3 + j] * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+f_l, t_ms=self.enc['t_pixel'])


class PasokonEncoder(Encoder):
    opts = {
        'P3': {
            't_pixel': 0.2083,
            'vis': 113,
            'width': 640,
            'height': 496,
            'sync_hz': 1200,
            'sync_ms': 5.208,
            't1_hz': 1500,
            't1_ms': 1.042
        },
        'P5': {
            't_pixel': 0.3125,
            'vis': 114,
            'width': 640,
            'height': 496,
            'sync_hz': 1200,
            'sync_ms': 7.813,
            't1_hz': 1500,
            't1_ms': 1.563
        },
        'P7': {
            't_pixel': 0.4167,
            'vis': 115,
            'width': 640,
            'height': 496,
            'sync_hz': 1200,
            'sync_ms': 10.417,
            't1_hz': 1500,
            't1_ms': 2.083
        }
    }

    def __init__(self, f, wav, mode='P3', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using PasokonEncoder with mode {mode}')


    def encode_line(self, line):
        self.generate_tone(f_hz=self.enc['sync_hz'], t_ms=self.enc['sync_ms'])
        self.generate_tone(f_hz=self.enc['t1_hz'], t_ms=self.enc['t1_ms'])

        for j in [0, 1, 2]: # RGB
            for i in range(0, self.enc['width']):
                # f_l = (line[i*3 + j] * (self.lum_w_hz - self.lum_b_hz)) / self.lum_max
                f_l = line[i*3 + j] * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+f_l, t_ms=self.enc['t_pixel'])

            self.generate_tone(f_hz=self.enc['t1_hz'], t_ms=self.enc['t1_ms'])


class PDEncoder(Encoder):
    opts = {
        'PD50': {
            'vis': 93,
            'width': 320,
            'height': 256,
            'y_scan_ms': 0.286,
        },
        'PD90': {
            'vis': 99,
            'width': 320,
            'height': 256,
            'y_scan_ms': 0.532,
        },
        'PD120': {
            'vis': 95,
            'width': 640,
            'height': 496,
            'y_scan_ms': 0.19,
        },
        'PD160': {
            'vis': 98,
            'width': 512,
            'height': 400,
            'y_scan_ms': 0.382,
        },
        'PD180': {
            'vis': 96,
            'width': 640,
            'height': 496,
            'y_scan_ms': 0.286,
        },
        'PD240': {
            'vis': 97,
            'width': 640,
            'height': 496,
            'y_scan_ms': 0.382,
        },
        'PD290': {
            'vis': 94,
            'width': 800,
            'height': 616,
            'y_scan_ms': 0.286,
        }
    }

    def __init__(self, f, wav, mode='PD50', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using PDEncoder with mode {mode}')
        self.sync_hz = 1200
        self.sync_ms = 20
        self.t1_hz = 1500
        self.t1_ms = 2.080
        self.odd_line = False


    def encode_line(self, line):
        w = self.enc['width']

        if self.odd_line:
            self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)
            self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)

            for i in range(0, w):
                y = self.rgb_to_y(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+y, t_ms=self.enc['y_scan_ms'])

            for i in range(0, w):
                r_y = self.rgb_to_ry(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+r_y, t_ms=self.enc['y_scan_ms'])

            for i in range(0, w):
                b_y = self.rgb_to_by(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+b_y, t_ms=self.enc['y_scan_ms'])

        else:
            for i in range(0, w):
                y = self.rgb_to_y(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+y, t_ms=self.enc['y_scan_ms'])

        self.odd_line = not self.odd_line


class RobotEncoder(Encoder):
    opts = {
        '36': {
            'vis': 8,
            'width': 320,
            'height': 240,
            'esep_hz': 1500,
            'y_scan_ms': 0.275,
            'ry_scan_ms': 0.1375,
            'by_scan_ms': 0.1375
        },
        '72': {
            'vis': 12,
            'width': 320,
            'height': 240,
            'y_scan_ms': 0.43125,
            'ry_scan_ms': 0.215625,
            'by_scan_ms': 0.215625
        }
    }

    def __init__(self, f, wav, mode='36', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using RobotEncoder with mode {mode}')
        self.sync_hz = 1200
        self.sync_ms = 9
        self.t1_hz = 1500
        self.t1_ms = 3
        self.t2_hz = 1900
        self.t2_ms = 1.5
        self.t3_hz = 1500
        self.t3_ms = 1.5
        self.esep_hz = 1500
        self.esep_ms = 4.5
        self.osep_hz = 2300
        self.osep_ms = 4.5
        self.odd_line = False


    def encode_line(self, line):
        w = self.enc['width']
        self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)
        self.generate_tone(f_hz=self.t1_hz, t_ms=self.t1_ms)

        for i in range(0, w):
            y = self.rgb_to_y(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
            self.generate_tone(f_hz=self.lum_b_hz+y, t_ms=self.enc['y_scan_ms'])

        if self.mode == '36':
            if self.odd_line:
                self.generate_tone(f_hz=self.osep_hz, t_ms=self.osep_ms)
                self.generate_tone(f_hz=self.t2_hz, t_ms=self.t2_ms)
                for i in range(0, w):
                    b_y = self.rgb_to_by(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                    self.generate_tone(f_hz=self.lum_b_hz+b_y, t_ms=self.enc['by_scan_ms'])
            else:    
                self.generate_tone(f_hz=self.esep_hz, t_ms=self.esep_ms)
                self.generate_tone(f_hz=self.t2_hz, t_ms=self.t2_ms)
                for i in range(0, w):
                    r_y = self.rgb_to_ry(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                    self.generate_tone(f_hz=self.lum_b_hz+r_y, t_ms=self.enc['ry_scan_ms'])

            self.odd_line = not self.odd_line

        elif self.mode == '72':
            self.generate_tone(f_hz=self.esep_hz, t_ms=self.esep_ms)
            self.generate_tone(f_hz=self.t2_hz, t_ms=self.t2_ms)
            for i in range(0, w):
                r_y = self.rgb_to_ry(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+r_y, t_ms=self.enc['ry_scan_ms'])

            self.generate_tone(f_hz=self.osep_hz, t_ms=self.osep_ms)
            self.generate_tone(f_hz=self.t3_hz, t_ms=self.t3_ms)
            for i in range(0, w):
                b_y = self.rgb_to_by(line[i*3], line[i*3+1], line[i*3+2]) * 3.1372549
                self.generate_tone(f_hz=self.lum_b_hz+b_y, t_ms=self.enc['by_scan_ms'])


class FAXEncoder(Encoder):
    opts = {
        'FAX480': {
            't_pixel': 0.512,
            'vis': 85,
            'width': 512,
            'height': 480
        }
    }

    def __init__(self, f, wav, mode='FAX480', sr=44100):
        assert mode in self.opts
        self.mode = mode
        self.enc = self.opts[self.mode]
        super().__init__(f, wav, sr)
        print(f'[.] Using FAXEncoder with mode {mode}')
        self.sync_hz = 1200
        self.sync_ms = 5.12
        self.t1_hz = 1500
        self.t1_ms = 0.5


    #@override
    def generate_header(self):
        for _ in range(1220):
            self.generate_tone(f_hz=2300, t_ms=2.05)
            self.generate_tone(f_hz=1500, t_ms=2.05)


    def generate_phasing_interval(self):
        for _ in range(20):
            self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)
            for i in range(0, self.enc['width']):
                self.generate_tone(f_hz=self.lum_w_hz, t_ms=self.enc['t_pixel'])


    def encode_line(self, line):
        self.generate_tone(f_hz=self.sync_hz, t_ms=self.sync_ms)

        for i in range(0, self.enc['width']):
            # wacky RGB->monochrome conversion
            mono = 0.3*line[i*3] + 0.59*line[i*3 + 1] + 0.11*line[i*3 + 2] 
            # f_l = (mono * (self.lum_w_hz - self.lum_b_hz)) / self.lum_max
            f_l = mono * 3.1372549
            self.generate_tone(f_hz=self.lum_b_hz+f_l, t_ms=self.enc['t_pixel'])
