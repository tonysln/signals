#!/usr/bin/env python3


import numpy as np
from PIL import Image
from typing import TypedDict


# https://www.sstv-handbook.com/download/sstv_03.pdf
# https://www.sstv-handbook.com/download/sstv_04.pdf

# sync  1200 Hz
# black 1500 Hz
# white 2300 Hz

# horizontal scan 16.6 Hz
# vertical   scan 0.1388 Hz

# 1. VIS code
# Vertical synchronization is used to detect the start of transmission
#The VIS contains digital code, the first and last bits are the start and stop bits with
#1200 Hz frequency. The remaining 8 bits provide mode identification and contain
#one parity bit. Each bit is transmitted in order from the least significant b

class EncodingProtocol(TypedDict):
    lum_max: int
    f_white: int
    f_black: int
    f_sync: int
    t_sync: int
    t_G: int
    t_B: int
    t_R: int
    t_1: int
    f_1: int


martinM1: EncodingProtocol = {
    'lum_max': 255,
    'f_white': 2300,
    'f_black': 1500,
    'f_sync': 1200,
    't_sync': 4.862,
    't_1': 0.572,
    'f_1': 1500,
    't_pixel': 0.572,
}

MODES = {
    'Martin_M1': martinM1
}

# TODO! just for testing
phase = 0.0


def generate_tone(f_hz, t_ms, f, SR=22050, chunk_size=1024):
    global phase

    t_s = t_ms / 1000.0
    total_samples = int(SR * t_s)
    phase_inc = 2 * np.pi * f_hz / SR

    samples_written = 0
    while samples_written < total_samples:
        n = min(chunk_size, total_samples - samples_written)
        t = phase + np.arange(n) * phase_inc
        chunk = np.sin(t)
        phase = (t[-1] + phase_inc) % (2 * np.pi) # TODO
        pcm16 = (chunk * 32767).astype(np.int16)
        f.write(pcm16.tobytes())
        
        samples_written += n

    return samples_written


def encode_line(line, f, enc: EncodingProtocol):
    generate_tone(f_hz=enc['f_sync'], t_ms=enc['t_sync'], f=f)
    generate_tone(f_hz=enc['f_1'], t_ms=enc['t_1'], f=f)

    # G*256, B*256, R*256
    for j in [1, 2, 0]:
        for i in range(0, 256):
            f_l = enc['f_black'] + ((line[i, j] * (enc['f_white'] - enc['f_black'])) / enc['lum_max'])
            t_l = enc['t_pixel']
            generate_tone(f_hz=f_l, t_ms=t_l, f=f)

        generate_tone(f_hz=enc['f_1'], t_ms=enc['t_1'], f=f)


def encode(img_path, out_path, vis, mode='Martin_M1'):
    f = open(out_path, 'wb')

    # 1. Calibration header
    generate_tone(f_hz=1900, t_ms=300, f=f)
    generate_tone(f_hz=1200, t_ms=10, f=f)
    generate_tone(f_hz=1900, t_ms=300, f=f)

    # 2. VIS code
    generate_tone(f_hz=1200, t_ms=30, f=f) # start bit

    for bit in vis[::-1]: # LSB, 7 data + 1 parity
        hz = 1100 if bit else 1300
        generate_tone(f_hz=hz, t_ms=30, f=f)
    
    generate_tone(f_hz=1200, t_ms=30, f=f) # stop bit

    # 3. RGB Scanlines
    img = Image.open(img_path).convert('RGB')
    data = np.asarray(img, dtype=np.float32) / 255.0

    for y in range(data.shape[0]):
        encode_line(data[y], f, MODES[mode])
        generate_tone(f_hz=1200, t_ms=5, f=f) # sync pulse

    f.close()


def decode(data, mode):
    pass


encode(img_path='test1.png', out_path='test.pcm', vis=[1,0,1,0,1,1,0,0], mode='Martin_M1')
print('Done.')

# ffmpeg -f s16le -ar 22050 -ac 2 -i test.pcm -f alsa default 
