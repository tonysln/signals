/*
  img.c

  Resources:
  https://www.libpng.org/pub/png/book/chapter13.html
  https://git.fmrib.ox.ac.uk/fsl/miscvis/-/tree/2007.0
  https://web.cs.ucdavis.edu/~amenta/s04/image/
  https://www.tspi.at/2020/03/20/libjpegexample.html#gsc.tab=0
  http://apodeline.free.fr/DOC/libjpeg/libjpeg-2.html
    
  Build:
  gcc -O3 -shared -fPIC img.c -o libimg.so -lpng -lz -ljpeg
*/

#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <jpeglib.h>
#include <jerror.h>
#include "readPNG.c"
#include "readBMP.c"


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

int load_jpg(const char *path, unsigned char **out, unsigned long *width, unsigned long *height) {
    struct jpeg_decompress_struct info;
    struct jpeg_error_mgr err;
    unsigned long int iw, ih, ic, bsize, sclen, sccnt;
    unsigned char* buf;
    JSAMPROW lineBuf;

    FILE *fp = fopen(path, "rb");
    if (!fp) 
        return -1;

    info.err = jpeg_std_error(&err);
    jpeg_create_decompress(&info);

    jpeg_stdio_src(&info, fp);
    jpeg_read_header(&info, TRUE);
    if (!jpeg_start_decompress(&info)) {
        jpeg_destroy_decompress(&info);
        fclose(fp);
        return -2;
    }

    iw = info.output_width;
    ih = info.output_height;
    ic = info.output_components;

    bsize = iw * ih * 3;
    buf = (unsigned char*) malloc(sizeof(unsigned char)*bsize);
    if (!buf) {
        jpeg_destroy_decompress(&info);
        fclose(fp);
        return -3;
    }

    sclen = iw * ic;
    sccnt = 0;

    while (info.output_scanline < info.output_height) {
        lineBuf = (buf + (sccnt * sclen));
        if (!jpeg_read_scanlines(&info, &lineBuf, 1)) {
            jpeg_destroy_decompress(&info);
            fclose(fp);
            return -4;
        }
        sccnt++;
    }

    *out = buf;
    *width = iw;
    *height = ih;

    bool ok = jpeg_finish_decompress(&info);
    jpeg_destroy_decompress(&info);
    fclose(fp);
    if (!ok)
        return -5;

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