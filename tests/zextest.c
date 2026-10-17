/* Runs ZEXDOC/ZEXALL (CP/M .COM) against the Z80 core.
 * Build: cc -O2 -Isrc tests/zextest.c src/z80.c -o zextest
 * Usage: ./zextest zexdoc.com */
#include <stdio.h>
#include <stdlib.h>
#include "z80.h"

static uint8_t mem[65536];
static uint8_t rd(void *c, uint16_t a) { (void)c; return mem[a]; }
static void wr(void *c, uint16_t a, uint8_t v) { (void)c; mem[a] = v; }
static uint8_t in(void *c, uint16_t p) { (void)c; (void)p; return 0xff; }
static void out(void *c, uint16_t p, uint8_t v) { (void)c; (void)p; (void)v; }

int main(int argc, char **argv)
{
    if (argc < 2) { fprintf(stderr, "usage: %s file.com\n", argv[0]); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 2; }
    fread(mem + 0x100, 1, 0xff00, f);
    fclose(f);
    Z80 z;
    z80_reset(&z);
    z.read = rd; z.write = wr; z.in = in; z.out = out;
    z.pc = 0x100; z.sp = 0xf000;
    mem[0] = 0x76;               /* warm boot -> HALT */
    mem[5] = 0xc9;               /* BDOS -> RET, intercepted below */
    for (;;) {
        if (z.pc == 5) {
            if (z.c == 2) putchar(z.e);
            else if (z.c == 9) for (uint16_t a = z.de; mem[a] != '$'; a++) putchar(mem[a]);
            fflush(stdout);
        }
        if (z.pc == 0) break;
        z80_step(&z);
    }
    printf("\n");
    return 0;
}
