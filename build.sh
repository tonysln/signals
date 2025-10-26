#!/bin/bash


gcc -O3 -shared -fPIC ./utils/FFT.c -o ./lib/libfft.so
gcc -O3 -shared -fPIC ./utils/img.c -o ./lib/libimg.so -lpng -lz -ljpeg
