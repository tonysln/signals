/*
  img.c

  Resources:
  https://www.libpng.org/pub/png/book/chapter13.html
  https://git.fmrib.ox.ac.uk/fsl/miscvis/-/tree/2007.0
  https://web.cs.ucdavis.edu/~amenta/s04/image/
    
  Build:
  gcc -O3 -shared -fPIC img.c -o libimg.so -lpng -lz -ltiff
*/

#include <stdlib.h>
#include <stdio.h>
#include "readpng.c"
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

int load_tiff(const char *path, unsigned char **out, unsigned long *width, unsigned long *height) {
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