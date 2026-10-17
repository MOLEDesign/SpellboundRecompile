/* Analysis helper: runs the game headlessly and reports which code writes
 * into screen memory (and where it was reading from just before), to
 * locate the sprite/room drawing routines.
 *   cc -O2 -Isrc tools/trace_writes.c src/z80.c -o trace_writes
 *   ./trace_writes S_BND128.TAP FROM_FRAME TO_FRAME [key-frame:key:len ...]
 */
#include "../src/spectrum.c"

static uint32_t wcount[65536];
static uint32_t rsrc[65536][4]; /* histogram of read address pages before a screen write */
static uint16_t last_read;
static Spectrum S;
static int active;

static uint8_t hook_read(void *ctx, uint16_t a)
{
    if (active && a != S.cpu.pc) last_read = a;
    return mem_read(ctx, a);
}

static void hook_write(void *ctx, uint16_t a, uint8_t v)
{
    if (active && a >= 0x4000 && a < 0x5800) {
        uint16_t pc = S.cpu.pc;
        wcount[pc]++;
        rsrc[pc][(last_read >> 14) & 3]++;
    }
    mem_write(ctx, a, v);
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "usage: %s tap from to [frame:key:len...]\n", argv[0]); return 2; }
    char err[256];
    if (spec_load_spellbound_tap(&S, argv[1], err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
    S.cpu.read = hook_read;
    S.cpu.write = hook_write;
    int from = atoi(argv[2]), to = atoi(argv[3]);
    for (int f = 0; f < to; f++) {
        for (int i = 4; i < argc; i++) {
            int kf, len; char key[16];
            if (sscanf(argv[i], "%d:%15[^:]:%d", &kf, key, &len) != 3) continue;
            int row = -1, bit = 0;
            if (!strcmp(key, "space")) { row = 7; bit = 0; }
            else if (!strcmp(key, "z")) { row = 0; bit = 1; }
            else if (!strcmp(key, "m")) { row = 7; bit = 2; }
            else if (!strcmp(key, "n")) { row = 7; bit = 3; }
            else if (!strcmp(key, "a")) { row = 1; bit = 0; }
            if (row < 0) continue;
            if (f == kf) spec_key(&S, row, bit, 1);
            if (f == kf + len) spec_key(&S, row, bit, 0);
        }
        active = f >= from;
        spec_run_frame(&S);
    }
    /* note: PC recorded is the address *after* the opcode fetch began; good enough to find routines */
    for (int pc = 0; pc < 65536; pc++)
        if (wcount[pc] > 50)
            printf("%04X writes=%7u  src pages: 0:%u 4000:%u 8000:%u C000:%u\n", pc, wcount[pc],
                   rsrc[pc][0], rsrc[pc][1], rsrc[pc][2], rsrc[pc][3]);
    return 0;
}
