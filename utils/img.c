/*
  img.c

  Resources:
  https://www.libpng.org/pub/png/book/chapter13.html
  https://git.fmrib.ox.ac.uk/fsl/miscvis/-/tree/2007.0
  https://web.cs.ucdavis.edu/~amenta/s04/image/
  https://libtiff.gitlab.io/libtiff/libtiff.html
  https://stackoverflow.com/a/38480562
    
  Build:
  gcc -O3 -shared -fPIC img.c -o libimg.so -lpng -lz -ltiff
*/

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include "readpng.c"
#include "readBMP.c"
#include "tiffio.h"


int load_png(const char *path, unsigned char **out, unsigned long *width, unsigned long *height) {
    unsigned char bg_red=0, bg_green=0, bg_blue=0;
    double display_exponent = 1.0 * 2.2;
    unsigned long image_rowbytes;
    int image_channels;

    FILE *fp = fopen(path, "rb");
    if (!fp) 
        return -1;

    readpng_init(fp, width, height);
    readpng_get_bgcolor(&bg_red, &bg_green, &bg_blue);

    *out = readpng_get_image(display_exponent, &image_channels, &image_rowbytes);
    
    readpng_cleanup(FALSE);
    fclose(fp);
    return 0;
}

int load_tiff(const char *path, unsigned char **out, unsigned long *width, unsigned long *height) {
    uint32_t w, h;
    uint32* raster;
    unsigned char *buf;

    TIFF* tiff = TIFFOpen(path, "r");
    if (!tiff)
        return -1;

    if (TIFFGetField(tiff,TIFFTAG_IMAGEWIDTH, &w) != 1) {
        TIFFClose(tiff);
        return -2;
    }

    if (TIFFGetField(tiff,TIFFTAG_IMAGELENGTH, &h) != 1) {
        TIFFClose(tiff);
        return -3;
    }

    *width = (unsigned long) w;
    *height = (unsigned long) h;

    raster = (uint32*) _TIFFmalloc(w*h * sizeof (uint32_t));
    if (!raster) {
        TIFFClose(tiff);
        return -4;
    }
    
    if (!TIFFReadRGBAImage(tiff, w, h, raster, 0)) {
        _TIFFfree(raster);
        TIFFClose(tiff);
        return -5;
    }

    buf = (unsigned char *) malloc(w*h * 3);
    if (!buf) {
        _TIFFfree(raster);
        TIFFClose(tiff);
        return -6;
    }

    for (uint32 i = 0, j = 0; i < w*h; ++i) {
        uint32 p = raster[i];
        buf[j++] = TIFFGetR(p);
        buf[j++] = TIFFGetG(p);
        buf[j++] = TIFFGetB(p);
    }

    *out = buf;

    _TIFFfree(raster);
    TIFFClose(tiff);
    return 0;
}

int load_bmp(const char *path, unsigned char **out, unsigned long *width, unsigned long *height) {
    Image *image;

    FILE *fp = fopen(path, "rb");
    if (!fp) 
        return -1;

    image = (Image *) malloc(sizeof(Image));
    if (!ImageLoad(fp, image))
        return -2;

    *width = image->sizeX;
    *height = image->sizeY;
    *out = image->data;

    free(image);
    fclose(fp);
    return 0;
}

void free_image(unsigned char *data) {
    free(data);
    data = NULL;
}