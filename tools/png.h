/* Tiny dependency-free PNG writer (uncompressed deflate), RGBA input 0xAARRGGBB. */
#ifndef TOOLS_PNG_H
#define TOOLS_PNG_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t png_crc_table[256];

static uint32_t png_crc(uint32_t c, const uint8_t *p, size_t n)
{
    if (!png_crc_table[1])
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t k = i;
            for (int j = 0; j < 8; j++) k = (k & 1) ? 0xEDB88320u ^ (k >> 1) : k >> 1;
            png_crc_table[i] = k;
        }
    c ^= 0xffffffffu;
    while (n--) c = png_crc_table[(c ^ *p++) & 0xff] ^ (c >> 8);
    return c ^ 0xffffffffu;
}

static void png_be32(uint8_t *p, uint32_t v) { p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v; }

static void png_chunk(FILE *f, const char *type, const uint8_t *data, uint32_t len)
{
    uint8_t hdr[8];
    png_be32(hdr, len);
    memcpy(hdr + 4, type, 4);
    fwrite(hdr, 1, 8, f);
    if (len) fwrite(data, 1, len, f);
    uint32_t c = png_crc(0, hdr + 4, 4);
    c = png_crc(c, data, len);
    uint8_t cb[4];
    png_be32(cb, c);
    fwrite(cb, 1, 4, f);
}

static int write_png(const char *path, const uint32_t *px, int w, int h, int stride)
{
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return -1; }
    size_t rawlen = (size_t)h * (1 + w * 4);
    uint8_t *raw = malloc(rawlen);
    for (int y = 0; y < h; y++) {
        uint8_t *r = raw + (size_t)y * (1 + w * 4);
        r[0] = 0;
        for (int x = 0; x < w; x++) {
            uint32_t c = px[(size_t)y * stride + x];
            r[1 + x * 4] = c >> 16; r[2 + x * 4] = c >> 8; r[3 + x * 4] = c; r[4 + x * 4] = c >> 24;
        }
    }
    size_t nblocks = (rawlen + 65534) / 65535;
    size_t zlen = 2 + rawlen + nblocks * 5 + 4;
    uint8_t *z = malloc(zlen), *o = z;
    *o++ = 0x78; *o++ = 0x01;
    uint32_t a = 1, b = 0;
    for (size_t i = 0; i < rawlen; i++) { a = (a + raw[i]) % 65521; b = (b + a) % 65521; }
    for (size_t off = 0; off < rawlen; off += 65535) {
        size_t n = rawlen - off < 65535 ? rawlen - off : 65535;
        *o++ = off + n >= rawlen;
        *o++ = n & 0xff; *o++ = n >> 8; *o++ = ~n & 0xff; *o++ = (~n >> 8) & 0xff;
        memcpy(o, raw + off, n);
        o += n;
    }
    png_be32(o, (b << 16) | a);
    o += 4;
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', 13, 10, 26, 10};
    fwrite(sig, 1, 8, f);
    uint8_t ihdr[13];
    png_be32(ihdr, w); png_be32(ihdr + 4, h);
    ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    png_chunk(f, "IHDR", ihdr, 13);
    png_chunk(f, "IDAT", z, (uint32_t)(o - z));
    png_chunk(f, "IEND", NULL, 0);
    fclose(f);
    free(raw);
    free(z);
    return 0;
}
#endif
