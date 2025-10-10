#!/usr/bin/env python3

from PIL import Image
from typing import TypedDict
import math
import struct

# https://www.sstv-handbook.com/download/sstv_03.pdf
# https://www.sstv-handbook.com/download/sstv_04.pdf
# http://lionel.cordesses.free.fr/gpages/Cordesses.pdf
# https://web.archive.org/web/20241227121817/http://www.barberdsp.com/downloads/Dayton%20Paper.pdf


class EncodingProtocol(TypedDict):
    lum_max: float
    f_white: float
    f_black: float
    f_sync: float
    t_sync: float
    t_1: float
    f_1: float
    t_pixel: float
    f_head_hi: float
    f_head_lo: float
    t_head_hi: float
    t_head_lo: float
    vis_code: list
    parity: bool
    width: int
    height: int


martinM1: EncodingProtocol = {
    'lum_max': 255,
    'f_white': 2300,
    'f_black': 1500,
    'f_sync': 1200,
    't_sync': 4.862,
    't_1': 0.572,
    'f_1': 1500,
    't_pixel': 0.572,
    'f_head_hi': 1900,
    'f_head_lo': 1200,
    't_head_hi': 300,
    't_head_lo': 10,
    'vis_code': [0,1,0,1,1,0,0],
    'parity': True,
    'width': 320,
    'height': 256
}

scottieS1: EncodingProtocol = {
    'lum_max': 255,
    'f_white': 2300,
    'f_black': 1500,
    'f_sync': 1200,
    't_sync': 9,
    't_1': 1.5,
    'f_1': 1500,
    't_pixel': 0.4320,
    'f_head_hi': 1900,
    'f_head_lo': 1200,
    't_head_hi': 300,
    't_head_lo': 10,
    'vis_code': [0,1,1,1,1,0,0],
    'parity': True,
    'width': 320,
    'height': 256
}

MODES = {
    'Martin_M1': martinM1,
    'Scottie_S1': scottieS1
}


class Encoder():
    def __init__(self, f, mode='Martin_M1', samp_rate=44100):
        assert mode in MODES

        self.mode = mode
        self.enc = MODES[mode]
        self.phase = 0.0
        self.SR = samp_rate
        self.A = 32767
        self.f = f
        self.first_line_done = False


    def generate_tone(self, f_hz, t_ms):
        total_samples = int(self.SR * (t_ms / 1000.0))
        phase_inc = 2 * math.pi * f_hz / self.SR

        b = b''
        i = 0
        while i < total_samples:
            sample = max(-self.A, min(self.A, int(self.A * math.sin(self.phase))))
            self.phase = (self.phase + phase_inc) % (2 * math.pi)
            b += struct.pack('<h', sample)
            i += 1

        # print(b)
        self.f.write(b)

        return i


    def encode_line(self, line, w):
        if self.mode == 'Martin_M1':
            self.generate_tone(f_hz=self.enc['f_sync'], t_ms=self.enc['t_sync'])
            self.generate_tone(f_hz=self.enc['f_1'], t_ms=self.enc['t_1'])

            for j in [1, 2, 0]: # GBR
                for i in range(0, w):
                    f_l = (line[i*3 + j] * (self.enc['f_white'] - self.enc['f_black'])) / self.enc['lum_max']
                    self.generate_tone(f_hz=self.enc['f_black']+f_l, t_ms=self.enc['t_pixel'])

                self.generate_tone(f_hz=self.enc['f_1'], t_ms=self.enc['t_1'])

        elif self.mode == 'Scottie_S1':
            if not self.first_line_done:
                self.generate_tone(f_hz=self.enc['f_sync'], t_ms=self.enc['t_sync'])
                self.first_line_done = True

            self.generate_tone(f_hz=self.enc['f_1'], t_ms=self.enc['t_1'])

            for j in [1, 2, 0]: # GBR
                for i in range(0, w):
                    f_l = (line[i*3 + j] * (self.enc['f_white'] - self.enc['f_black'])) / self.enc['lum_max']
                    self.generate_tone(f_hz=self.enc['f_black']+f_l, t_ms=self.enc['t_pixel'])

                if j == 2:
                    self.generate_tone(f_hz=self.enc['f_sync'], t_ms=self.enc['t_sync'])

                if j != 0:
                    self.generate_tone(f_hz=self.enc['f_1'], t_ms=self.enc['t_1'])


    def encode_image(self, data, h, w):
        for y in range(h):
            self.encode_line(data[y*w*3 : (y+1)*w*3], w)


    def generate_header(self):
        self.generate_tone(f_hz=self.enc['f_head_hi'], t_ms=self.enc['t_head_hi'])
        self.generate_tone(f_hz=self.enc['f_head_lo'], t_ms=self.enc['t_head_lo'])
        self.generate_tone(f_hz=self.enc['f_head_hi'], t_ms=self.enc['t_head_hi'])


    def generate_VIS(self):
        self.generate_tone(f_hz=1200, t_ms=30) # start bit

        for bit in self.enc['vis_code'][::-1]: # LSB, 7 data
            hz = 1100 if bit else 1300
            self.generate_tone(f_hz=hz, t_ms=30)
        
        hz = 1300 if self.enc['parity'] else 1100
        self.generate_tone(f_hz=hz, t_ms=30) # parity bit
        self.generate_tone(f_hz=1200, t_ms=30) # stop bit


    def __del__(self):
        self.f.close()



def encode(img_path, out_path, mode):
    f = open(out_path, 'wb')
    assert mode in MODES

    e = Encoder(f, mode)

    # 1. Calibration header
    e.generate_header()

    # 2. VIS code
    e.generate_VIS()

    # 3. RGB Scanlines
    img = Image.open(img_path).convert('RGB')
    img.thumbnail((e.enc['width'],e.enc['height']))
    w, h = img.size

    assert w <= e.enc['width']
    assert h <= e.enc['height']

    data = memoryview(img.tobytes())
    e.encode_image(data, h, w)

    e.__del__()
    if not f.closed:
        f.close()


def decode(data, mode):
    pass


encode(img_path='test1.png', out_path='test1_m1.pcm', mode='Martin_M1')
encode(img_path='test1.png', out_path='test1_s1.pcm', mode='Scottie_S1')
print('Done.')

# ffmpeg -f s16le -ar 22050 -ac 2 -i test.pcm -f alsa default 
