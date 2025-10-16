/*
  FFT.c

  Resources:
  https://www.robinscheibler.org/2013/02/13/real-fft.html
  https://antimatter15.com/2015/05/cooley-tukey-fft-dct-idct-in-under-1k-of-javascript/
    
  Build:
  gcc -O3 -shared -fPIC FFT.c -o libfft.so
*/

#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <float.h>


void fft(double *real, double *imag, int n) {
    int i, j, k, m;

    for (i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;

        for (; j & bit; bit >>= 1)
            j ^= bit;

        j ^= bit;

        if (i < j) {
            double tr = real[i];
            real[i] = real[j];
            real[j] = tr;
            double ti = imag[i];
            imag[i] = imag[j];
            imag[j] = ti;
        }
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = -2 * M_PI / len;
        double wlen_r = cos(ang);
        double wlen_i = sin(ang);

        for (i = 0; i < n; i += len) {
            double wr = 1, wi = 0;
            for (j = 0; j < len / 2; j++) {
                double ur = real[i + j], ui = imag[i + j];
                double vr = real[i + j + len/2] * wr - imag[i + j + len/2] * wi;
                double vi = real[i + j + len/2] * wi + imag[i + j + len/2] * wr;

                real[i + j] = ur + vr;
                imag[i + j] = ui + vi;
                real[i + j + len/2] = ur - vr;
                imag[i + j + len/2] = ui - vi;

                double nxt_wr = wr * wlen_r - wi * wlen_i;
                wi = wr * wlen_i + wi * wlen_r;
                wr = nxt_wr;
            }
        }
    }
}

void ifft(double *real, double *imag, int n) {
    fft(real, imag, n);
    for (int i = 0; i < n; i++) {
        real[i] /= n;
        imag[i] /= n;
    }
}

void dct(double *val, int n) {
    double *re = malloc(n * sizeof(double));
    double *im = malloc(n * sizeof(double));

    for (int i = 0, j = n; j > i; i++) {
        re[i] = val[i*2];
        re[--j] = val[i*2 + 1];
    }
    
    fft(re, im, n);
    
    double k = -M_PI / (2*n);
    for (int i = 0; i < n; i++) {
        val[i] = 2*re[i]*cos(k*i) - 2*im[i]*sin(k*i);
    }

    free(re);
    free(im);
}

void hann(double *val, int n) {
    for (int i = 0; i < n; i++) {
        val[i] = 0.5 * (1 - cos(2*M_PI * i/(n-1)));
    }
}

void filter(double *val, double* fval, int n) {
    for (int i = 0; i < n; i++) {
        val[i] = fval[i] * val[i];
    }
}

double fft_mag_pwr(double *real, double *imag, double *mag, int n) {
    double pwr = DBL_EPSILON;
    for (int i = 0; i < n; i++) {
        mag[i] = real[i]*real[i] + imag[i]*imag[i];
        pwr += mag[i];
    }
    pwr = pwr / n;
    return sqrt(pwr);
}