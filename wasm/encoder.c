/*
  encoder.c

  SSTV encoder, a C port of sstv/encoder.py for the browser (WebAssembly).
  Tones, timings and rounding follow the Python code so both produce the
  same samples.

  The host (JS) drives it:
    sstv_begin(mode, sr)       pick a mode, reset state; returns 0 or -1
    sstv_image()               RGB buffer (width*height*3, top row first)
    sstv_intro()               optional VOX leader tones
    sstv_header()              calibration header + VIS (or FAX phasing)
    sstv_line(y)               encode one image row
    sstv_finish()              flush the remaining samples

  Samples (signed 16-bit mono) are handed to the host in blocks through the
  imported function sstv_emit(ptr, count); the host copies them out.

  Mode table: sstv_mode_count(), sstv_mode_family(i), sstv_mode_name(i),
  sstv_mode_width(i), sstv_mode_height(i).

  Build:
  emcc -O3 --no-entry -sSTANDALONE_WASM -sALLOW_MEMORY_GROWTH \
       -sERROR_ON_UNDEFINED_SYMBOLS=0 encoder.c -o encoder.wasm
*/

#include <math.h>
#include <stdint.h>
#include <stdlib.h>

#define EXPORT __attribute__((used, visibility("default")))

__attribute__((import_module("env"), import_name("sstv_emit")))
extern void sstv_emit(const int16_t *samples, int count);

enum family { MARTIN, SCOTTIE, WRASSE, PASOKON, FAX, ROBOT, PD };

static const char *FAMILY_NAMES[] = {
    "Martin", "Scottie", "Wrasse", "Pasokon", "FAX", "Robot", "PD",
};

struct mode {
    enum family family;
    const char *name;
    int vis, width, height;
    double t_pixel;              /* or y_scan for Robot / PD */
    double ry_scan, by_scan;     /* Robot */
    double sync_ms, t1_ms;       /* Pasokon (per mode) */
};

static const struct mode MODES[] = {
    {MARTIN, "M1", 44, 320, 256, 0.0004576},
    {MARTIN, "M2", 40, 320, 256, 0.0002288},
    {MARTIN, "M3", 36, 320, 128, 0.0004576},
    {MARTIN, "M4", 32, 320, 128, 0.0002288},

    {SCOTTIE, "S1", 60, 320, 256, 0.000432},
    {SCOTTIE, "S2", 56, 320, 256, 0.0002752},
    {SCOTTIE, "S3", 52, 320, 128, 0.000432},
    {SCOTTIE, "S4", 48, 320, 128, 0.0002752},
    {SCOTTIE, "DX", 76, 320, 256, 0.00108},

    {WRASSE, "SC2-30", 51, 320, 128, 0.00018125},
    {WRASSE, "SC2-60", 59, 320, 256, 0.00018125},
    {WRASSE, "SC2-120", 63, 320, 256, 0.000365625},
    {WRASSE, "SC2-180", 55, 320, 256, 0.000734375},

    {PASOKON, "P3", 113, 640, 496, 0.0002083, 0, 0, 0.005208, 0.001042},
    {PASOKON, "P5", 114, 640, 496, 0.0003125, 0, 0, 0.007813, 0.001563},
    {PASOKON, "P7", 115, 640, 496, 0.0004167, 0, 0, 0.010417, 0.002083},

    {FAX, "FAX480", 85, 512, 480, 0.000512},

    {ROBOT, "36", 8, 320, 240, 0.000275, 0.0001375, 0.0001375},
    {ROBOT, "72", 12, 320, 240, 0.00043125, 0.000215625, 0.000215625},

    {PD, "PD50", 93, 320, 256, 0.000286},
    {PD, "PD90", 99, 320, 256, 0.000532},
    {PD, "PD120", 95, 640, 496, 0.00019},
    {PD, "PD160", 98, 512, 400, 0.000382},
    {PD, "PD180", 96, 640, 496, 0.000286},
    {PD, "PD240", 97, 640, 496, 0.000382},
    {PD, "PD290", 94, 800, 616, 0.000286},
};

#define N_MODES ((int)(sizeof(MODES) / sizeof(MODES[0])))

#define AMP 32767
#define LUM_B_HZ 1500
#define LUM_W_HZ 2300
#define LUM_SCALE 3.1372549
#define SYNC_HZ 1200
#define PORCH_HZ 1500
#define TWO_PI (2 * M_PI)

/* Encoder state */
static const struct mode *m;
static int sr;
static double phase, clock_s;
static long last_sample;
static int odd_line, first_line_done;
static uint8_t *image;

/* Output block handed to the host when full */
#define BLOCK 16384
static int16_t block[BLOCK];
static int block_len;


static void flush(void) {
    if (block_len) {
        sstv_emit(block, block_len);
        block_len = 0;
    }
}

/* Python's round(): half to even, which nearbyint() does by default */
static void tone(double f_hz, double t_s) {
    clock_s += t_s;
    long end_sample = (long)nearbyint(clock_s * sr);
    long total = end_sample - last_sample;
    double phase_inc = 2 * M_PI * f_hz / sr;

    for (long i = 0; i < total; i++) {
        double v = AMP * sin(phase);
        int s = (int)v;  /* truncates toward zero, like int() */
        if (s > AMP) s = AMP;
        if (s < -AMP) s = -AMP;
        phase = fmod(phase + phase_inc, TWO_PI);

        block[block_len++] = (int16_t)s;
        if (block_len == BLOCK)
            flush();
    }

    last_sample = end_sample;
}

static double rgb_to_y(int r, int g, int b) {
    return 16.0 + (0.003906 * ((65.738 * r) + (129.057 * g) + (25.064 * b)));
}

static double rgb_to_ry(int r, int g, int b) {
    return 128.0 + (0.003906 * ((112.439 * r) + (-94.154 * g) + (-18.285 * b)));
}

static double rgb_to_by(int r, int g, int b) {
    return 128.0 + (0.003906 * ((-37.945 * r) + (-74.494 * g) + (112.439 * b)));
}

/* One colour channel (0=R, 1=G, 2=B) of a row, one tone per pixel */
static void scan_channel(const uint8_t *line, int c, double t) {
    for (int i = 0; i < m->width; i++)
        tone(LUM_B_HZ + line[i * 3 + c] * LUM_SCALE, t);
}

enum yuv { Y, RY, BY };

static void scan_yuv(const uint8_t *line, enum yuv which, double t) {
    for (int i = 0; i < m->width; i++) {
        const uint8_t *p = line + i * 3;
        double v = which == Y  ? rgb_to_y(p[0], p[1], p[2])
                 : which == RY ? rgb_to_ry(p[0], p[1], p[2])
                               : rgb_to_by(p[0], p[1], p[2]);
        tone(LUM_B_HZ + v * LUM_SCALE, t);
    }
}


EXPORT int sstv_mode_count(void) { return N_MODES; }

EXPORT const char *sstv_mode_family(int i) {
    return i >= 0 && i < N_MODES ? FAMILY_NAMES[MODES[i].family] : 0;
}

EXPORT const char *sstv_mode_name(int i) {
    return i >= 0 && i < N_MODES ? MODES[i].name : 0;
}

EXPORT int sstv_mode_width(int i) {
    return i >= 0 && i < N_MODES ? MODES[i].width : 0;
}

EXPORT int sstv_mode_height(int i) {
    return i >= 0 && i < N_MODES ? MODES[i].height : 0;
}

EXPORT int sstv_begin(int mode, int samp_rate) {
    if (mode < 0 || mode >= N_MODES || samp_rate <= 0)
        return -1;

    free(image);
    m = &MODES[mode];
    image = malloc((size_t)m->width * m->height * 3);
    if (!image)
        return -1;

    sr = samp_rate;
    phase = clock_s = 0;
    last_sample = 0;
    odd_line = first_line_done = 0;
    block_len = 0;
    return 0;
}

EXPORT uint8_t *sstv_image(void) { return image; }

EXPORT void sstv_intro(void) {
    static const int hz[] = {1900, 1500, 1900, 1500, 2300, 1500, 2300, 1500};
    for (int i = 0; i < 8; i++)
        tone(hz[i], 0.1);
}

EXPORT void sstv_header(void) {
    if (m->family == FAX) {
        for (int i = 0; i < 1220; i++) {
            tone(2300, 0.00205);
            tone(1500, 0.00205);
        }
        /* Phasing interval */
        for (int i = 0; i < 20; i++) {
            tone(SYNC_HZ, 0.00512);
            for (int x = 0; x < m->width; x++)
                tone(LUM_W_HZ, m->t_pixel);
        }
        return;
    }

    tone(1900, 0.3);
    tone(1200, 0.01);
    tone(1900, 0.3);

    /* VIS: start bit, 7 data bits LSB first, even parity, stop bit */
    tone(1200, 0.03);
    int ones = 0;
    for (int i = 0; i < 7; i++) {
        int bit = (m->vis >> i) & 1;
        ones += bit;
        tone(bit ? 1100 : 1300, 0.03);
    }
    tone(ones % 2 == 0 ? 1300 : 1100, 0.03);
    tone(1200, 0.03);
}

EXPORT void sstv_line(int y) {
    if (y < 0 || y >= m->height)
        return;

    const uint8_t *line = image + (size_t)y * m->width * 3;
    double t = m->t_pixel;

    switch (m->family) {
    case MARTIN:
        tone(SYNC_HZ, 0.004862);
        tone(PORCH_HZ, 0.000572);
        for (int c = 1, k = 0; k < 3; k++, c = (c + 1) % 3) {  /* G, B, R */
            scan_channel(line, c, t);
            tone(PORCH_HZ, 0.000572);
        }
        break;

    case SCOTTIE:
        if (!first_line_done) {
            tone(SYNC_HZ, 0.009);
            first_line_done = 1;
        }
        tone(PORCH_HZ, 0.0015);
        scan_channel(line, 1, t);       /* G */
        tone(PORCH_HZ, 0.0015);
        scan_channel(line, 2, t);       /* B */
        tone(SYNC_HZ, 0.009);
        tone(PORCH_HZ, 0.0015);
        scan_channel(line, 0, t);       /* R */
        break;

    case WRASSE:
        tone(SYNC_HZ, 0.0055225);
        tone(PORCH_HZ, 0.0005);
        for (int c = 0; c < 3; c++)
            scan_channel(line, c, t);
        break;

    case PASOKON:
        tone(SYNC_HZ, m->sync_ms);
        tone(PORCH_HZ, m->t1_ms);
        for (int c = 0; c < 3; c++) {
            scan_channel(line, c, t);
            tone(PORCH_HZ, m->t1_ms);
        }
        break;

    case FAX:
        tone(SYNC_HZ, 0.00512);
        for (int i = 0; i < m->width; i++) {
            const uint8_t *p = line + i * 3;
            double mono = 0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2];
            tone(LUM_B_HZ + mono * LUM_SCALE, t);
        }
        break;

    case ROBOT:
        tone(SYNC_HZ, 0.009);
        tone(PORCH_HZ, 0.003);
        scan_yuv(line, Y, t);
        if (m->vis == 8) {  /* Robot 36: alternate R-Y / B-Y */
            if (odd_line) {
                tone(2300, 0.0045);
                tone(1900, 0.0015);
                scan_yuv(line, BY, m->by_scan);
            } else {
                tone(1500, 0.0045);
                tone(1900, 0.0015);
                scan_yuv(line, RY, m->ry_scan);
            }
            odd_line = !odd_line;
        } else {            /* Robot 72 */
            tone(1500, 0.0045);
            tone(1900, 0.0015);
            scan_yuv(line, RY, m->ry_scan);
            tone(2300, 0.0045);
            tone(1500, 0.0015);
            scan_yuv(line, BY, m->by_scan);
        }
        break;

    case PD:
        if (odd_line) {
            tone(SYNC_HZ, 0.02);
            tone(PORCH_HZ, 0.00208);
            scan_yuv(line, Y, t);
            scan_yuv(line, RY, t);
            scan_yuv(line, BY, t);
        } else {
            scan_yuv(line, Y, t);
        }
        odd_line = !odd_line;
        break;
    }
}

EXPORT void sstv_finish(void) { flush(); }
