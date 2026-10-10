/*
  goertzel.c

  Detects a single tone in an audio signal. Gives the same answer as the
  Goertzel algorithm, the power of one frequency over a window of samples,
  but from running sums, so that any window costs the same after one pass
  over the signal.

  Resources:
  https://remcycles.net/blog/goertzel.html
  https://en.wikipedia.org/wiki/Goertzel_algorithm
*/

#include <math.h>
#include <stdint.h>


void goertzel_sums(const int16_t *pcm, int n, double hz, double sr, double *sums) {
    double w = 2 * M_PI * hz / sr;

    sums[0] = 0;
    sums[1] = 0;

    for (int i = 0; i < n; i++) {
        double x = pcm[i] / 32768.0;

        sums[2 * i + 2] = sums[2 * i] + x * cos(w * i);
        sums[2 * i + 3] = sums[2 * i + 1] + x * sin(w * i);
    }
}

static double sum_at(const double *sums, int n, double x) {
    if (x <= 0)
        return sums[0];
    if (x >= n)
        return sums[2 * n];

    int i = (int) x;
    return sums[2 * i] + (x - i) * (sums[2 * i + 2] - sums[2 * i]);
}

double goertzel(const double *sums, int n, double a, double b) {
    double re = sum_at(sums, n, b) - sum_at(sums, n, a);
    double im = sum_at(sums + 1, n, b) - sum_at(sums + 1, n, a);
    double half = (b - a) / 2;

    return (re * re + im * im) / (half * half);
}
