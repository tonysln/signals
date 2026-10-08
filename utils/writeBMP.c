/*
  writeBMP.c

  Resources:
  https://en.wikipedia.org/wiki/BMP_file_format
*/

#include <stdio.h>


/* Writes width*height*3 bytes of RGB, top row first, as a 24 bit BMP.
   return value = 0 for success, -1 for write error */
int writebmp_image(FILE *outfile, const unsigned char *data, unsigned long width, unsigned long height) {
    unsigned long pad = (4 - width * 3 % 4) % 4;
    unsigned long size = (width * 3 + pad) * height;
    unsigned char head[54] = {'B', 'M'};
    unsigned char zero[3] = {0};

    // Little endian header fields as {offset, value}: file size, data offset,
    // header size, width, height, planes (1) and bits per pixel (24), data size
    unsigned long fields[7][2] = {{2, 54 + size}, {10, 54}, {14, 40}, {18, width},
                                  {22, height}, {26, 1 | 24 << 16}, {34, size}};

    for (int i = 0; i < 7; i++)
        for (int j = 0; j < 4; j++)
            head[fields[i][0] + j] = fields[i][1] >> (8 * j);

    if (fwrite(head, 1, 54, outfile) != 54)
        return -1;

    // Rows go bottom up, pixels as BGR, every row padded to 4 bytes
    for (unsigned long y = height; y-- > 0;) {
        const unsigned char *row = data + y * width * 3;

        for (unsigned long x = 0; x < width; x++) {
            unsigned char bgr[3] = {row[x * 3 + 2], row[x * 3 + 1], row[x * 3]};
            if (fwrite(bgr, 1, 3, outfile) != 3)
                return -1;
        }

        if (fwrite(zero, 1, pad, outfile) != pad)
            return -1;
    }

    return 0;
}
