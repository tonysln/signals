import array
import ctypes
import itertools
import logging
import math
import os
import wave
from ctypes import POINTER, byref, c_double, c_int, c_ubyte, c_void_p

from encoder import *

logger = logging.getLogger(__name__)

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")

# Non-pixel parts of a line layout; pixel scans use the channel index (0..2)
SYNC = "sync"
GAP = "gap"


class DecodeError(Exception):
    pass


class Decoder:
    modes = {
        44: (MartinEncoder, "M1"),
        40: (MartinEncoder, "M2"),
        36: (MartinEncoder, "M3"),
        32: (MartinEncoder, "M4"),
        60: (ScottieEncoder, "S1"),
        56: (ScottieEncoder, "S2"),
        52: (ScottieEncoder, "S3"),
        48: (ScottieEncoder, "S4"),
        76: (ScottieEncoder, "DX"),
        51: (WrasseEncoder, "SC2-30"),
        59: (WrasseEncoder, "SC2-60"),
        63: (WrasseEncoder, "SC2-120"),
        55: (WrasseEncoder, "SC2-180"),
        113: (PasokonEncoder, "P3"),
        114: (PasokonEncoder, "P5"),
        115: (PasokonEncoder, "P7"),
        93: (PDEncoder, "PD50"),
        99: (PDEncoder, "PD90"),
        95: (PDEncoder, "PD120"),
        98: (PDEncoder, "PD160"),
        96: (PDEncoder, "PD180"),
        97: (PDEncoder, "PD240"),
        94: (PDEncoder, "PD290"),
        8: (RobotEncoder, "36"),
        12: (RobotEncoder, "72"),
        85: (FAXEncoder, "FAX480"),
    }

    # Leader, break, leader, VIS start bit
    header_hz = [1900, 1200, 1900, 1200]
    header_ms = [0.3, 0.01, 0.3, 0.03]
    vis_bit_ms = 0.03
    vis_hz = [1300, 1100]  # bit 0, bit 1

    def __init__(self, fc=1750, bw=2000, taps_ms=0.001):
        # Demodulator band: fc +- bw Hz, filter reaching taps_ms to each side.
        # Narrower and longer (bw=1000, taps_ms=0.002) holds up better in
        # noise, at the cost of horizontal sharpness.
        self.fc = fc
        self.bw = bw
        self.taps_ms = taps_ms

        self.sr = 0
        self.slen = 0
        self.pcm = b""
        self.cum = None

        self.load_libdemod()
        self.load_libfft()

    def load_libdemod(self):
        lib = ctypes.CDLL(os.path.join(LIB_DIR, "libdemod.so"))
        track = [POINTER(c_double), c_int]
        lib.fm_demod.argtypes = [
            c_void_p,
            c_int,
            c_double,
            c_double,
            c_double,
            c_int,
            c_double,
            c_double,
            POINTER(c_double),
        ]
        lib.fm_demod.restype = c_int
        lib.mean_hz.argtypes = track + [c_double, c_double]
        lib.mean_hz.restype = c_double
        lib.find_tones.argtypes = track + [
            c_double,
            c_double,
            POINTER(c_double),
            POINTER(c_double),
            c_int,
            c_double,
        ]
        lib.find_tones.restype = c_double
        lib.mean_hz_train.argtypes = track + [c_double, c_double, c_double, c_int]
        lib.mean_hz_train.restype = c_double
        lib.scan_pixels.argtypes = track + [
            c_double,
            c_double,
            c_int,
            c_double,
            c_double,
            c_void_p,
            c_int,
        ]
        lib.scan_pixels.restype = None
        self.lib = lib

    def load_libfft(self):
        lib = ctypes.CDLL(os.path.join(LIB_DIR, "libfft.so"))
        sums = [POINTER(c_double), c_int]
        lib.goertzel_sums.argtypes = [c_void_p, c_int, c_double, c_double, POINTER(c_double)]
        lib.goertzel_sums.restype = None
        lib.goertzel.argtypes = sums + [c_double, c_double]
        lib.goertzel.restype = c_double
        self.libfft = lib

    def read_wav(self, in_path):
        logger.info("Reading WAV samples...")

        with wave.open(in_path, "r") as f:
            if f.getsampwidth() != 2:
                raise DecodeError("Only 16 bit WAV files are supported")

            sr = f.getframerate()
            ch = f.getnchannels()
            pcm = f.readframes(f.getnframes())

        if ch > 1:
            pcm = array.array("h", pcm)[::ch].tobytes()

        self.demodulate(pcm, sr)

    def read_raw(self, in_path, sr):
        logger.info("Reading raw 16 bit mono samples...")

        with open(in_path, "rb") as f:
            pcm = f.read()

        self.demodulate(pcm[: len(pcm) & ~1], sr)

    def demodulate(self, pcm, sr):
        logger.info(f"Demodulating at sample rate {sr} Hz...")
        self.sr = sr
        self.pcm = pcm
        self.slen = len(pcm) // 2
        self.cum = (c_double * (self.slen + 1))()

        half = max(1, round(sr * self.taps_ms))
        res = self.lib.fm_demod(
            pcm, self.slen, sr, self.fc, self.bw, half, 1000, 2500, self.cum
        )
        if res != 0:
            raise DecodeError(f"Demodulation failed: error code {res}")

    def mean(self, t0, t1):
        # Mean frequency between two points in time
        return self.lib.mean_hz(self.cum, self.slen, t0 * self.sr, t1 * self.sr)

    def tone(self, hz, t0, t1):
        # Running sums of one tone between two points in time, for power()
        a = min(self.slen, max(0, round(t0 * self.sr)))
        b = min(self.slen, max(a, round(t1 * self.sr)))

        sums = (c_double * (2 * (b - a + 1)))()
        self.libfft.goertzel_sums(self.pcm[2 * a : 2 * b], b - a, hz, self.sr, sums)
        return sums, b - a, a

    def power(self, tone, t0, t1):
        # Power of that tone between two points in time, 1.0 is full scale
        sums, n, first = tone
        return self.libfft.goertzel(sums, n, t0 * self.sr - first, t1 * self.sr - first)

    def find_header(self, start=0.0, step=0.002, tol=200):
        # Returns the time of the VIS start bit
        # TODO find the header by tone power (goertzel) in short chunks, the
        # frequency track loses it in heavy noise
        # TODO FAX has its own header and a phasing interval, no VIS code
        n = len(self.header_hz)
        hz = (c_double * n)(*self.header_hz)
        ms = (c_double * n)(*[t * self.sr for t in self.header_ms])

        pos = self.lib.find_tones(
            self.cum, self.slen, start * self.sr, step * self.sr, hz, ms, n, tol
        )
        if pos < 0:
            return None

        return pos / self.sr + sum(self.header_ms[:-1])

    def decode_VIS(self, start):
        # Start bit, 7 data bits LSB first, even parity bit. A bit is
        # whichever of its two tones is stronger.
        step = self.vis_bit_ms
        zero, one = [self.tone(hz, start, start + step * 10) for hz in self.vis_hz]
        bits = [
            self.power(one, start + step * i, start + step * (i + 1))
            > self.power(zero, start + step * i, start + step * (i + 1))
            for i in range(1, 9)
        ]

        vis = sum(bit << i for i, bit in enumerate(bits[:7]))
        if sum(bits) % 2 != 0 or vis not in self.modes:
            return None

        return self.modes[vis]

    def line_layout(self, encoder):
        # One line as [(SYNC | GAP | channel, duration)], mirrors encode_line
        e = encoder.enc
        sync = (SYNC, e["sync_ms"] if "sync_ms" in e else encoder.sync_ms)
        gap = (GAP, e["t1_ms"] if "t1_ms" in e else encoder.t1_ms)
        scan = e.get("t_pixel", 0) * e["width"]

        if isinstance(encoder, MartinEncoder):
            return [sync, gap, (1, scan), gap, (2, scan), gap, (0, scan), gap]

        if isinstance(encoder, ScottieEncoder):
            return [gap, (1, scan), gap, (2, scan), sync, gap, (0, scan)]

        if isinstance(encoder, WrasseEncoder):
            return [sync, gap, (0, scan), (1, scan), (2, scan)]

        if isinstance(encoder, PasokonEncoder):
            return [sync, gap, (0, scan), gap, (1, scan), gap, (2, scan), gap]

        # TODO Robot and PD (YUV, lines sent in pairs), FAX (monochrome)
        raise DecodeError(f"Decoding {type(encoder).__name__} is not supported")

    def track_sync(self, start, layout, lines, reach=0.005, slant=0.003):
        # The transmitter's clock is steady, so the sync pulses sit on a
        # straight line in time: one pulse position and the line period fix
        # all the others. Both are found at once, as the timing whose pulse
        # windows have the lowest mean frequency. Corrects where the image
        # starts and how long a line really is (slant from sample rate
        # mismatch), within +-reach seconds and +-slant of the line period.
        # TODO correct a tuning offset from the frequency of the pulses
        kinds = [k for k, _ in layout]
        period = sum(t for _, t in layout)
        offset = sum(t for _, t in layout[: kinds.index(SYNC)])
        width = layout[kinds.index(SYNC)][1]
        mid = (lines - 1) / 2

        # A timing is the pulse of the middle line and the line period, which
        # can be searched one at a time
        def hz(timing):
            centre, period = timing
            return self.lib.mean_hz_train(
                self.cum,
                self.slen,
                (centre - mid * period) * self.sr,
                period * self.sr,
                width * self.sr,
                lines,
            )

        def around(x, step, reach):
            count = math.ceil(reach / step)
            return [x + step * i for i in range(-count, count + 1)]

        # Coarse search from the first line, in steps that keep most of every
        # pulse inside its window
        dc, dp = width / 2, width / lines / 2
        first, period = min(
            itertools.product(
                around(start + offset, dc, reach),
                around(period, dp, slant * period),
            ),
            key=lambda t: hz((t[0] + mid * t[1], t[1])),
        )

        # Then the steps are halved until they are well below one sample
        best = first + mid * period, period
        for _ in range(10):
            dc, dp = dc / 2, dp / 2
            best = min(
                itertools.product(around(best[0], dc, dc), around(best[1], dp, dp)),
                key=hz,
            )

        centre, period = best
        return centre - mid * period - offset, period

    def decode_image(self, start, encoder):
        w = encoder.enc["width"]
        h = encoder.enc["height"]
        layout = self.line_layout(encoder)

        nominal = sum(t for _, t in layout)
        start, period = self.track_sync(start, layout, h)
        layout = [(k, t * period / nominal) for k, t in layout]

        pixels = (c_ubyte * (w * h * 3))()
        for y in range(h):
            t = start + y * period
            for kind, dur in layout:
                if kind not in (SYNC, GAP):
                    self.lib.scan_pixels(
                        self.cum,
                        self.slen,
                        t * self.sr,
                        dur * self.sr,
                        w,
                        encoder.lum_b_hz,
                        encoder.lum_w_hz,
                        byref(pixels, y * w * 3 + kind),
                        3,
                    )

                t += dur

        return w, h, bytes(pixels)

    def decode(self, encoder=None):
        # Returns (width, height, RGB bytes). The mode is read from the VIS
        # code unless an encoder instance is given.
        start = self.find_header()
        if start is None:
            raise DecodeError("No SSTV header found")

        logger.info(f"Found header, VIS code at {start:.3f} s")

        if not encoder:
            vis = self.decode_VIS(start)
            if not vis:
                raise DecodeError("Unreadable VIS code, provide encoding and mode")

            enc, mode = vis
            logger.info(f"Detected {enc.__name__} mode {mode}")
            encoder = enc(mode=mode)

        # Start bit, 8 VIS bits, stop bit
        start += self.vis_bit_ms * 10

        # Scottie sends one extra sync pulse before the first line
        if isinstance(encoder, ScottieEncoder):
            start += encoder.sync_ms

        return self.decode_image(start, encoder)
