/* Renders game graphics by calling the game's own drawing code inside the
 * emulator, so formats that are packed or drawn with mirroring do not have
 * to be decoded by hand.
 *
 *   cc -O2 -Isrc tools/asset_render.c src/z80.c -o asset_render
 *   ./asset_render S_BND128.TAP OUTDIR
 *
 * Writes OUTDIR/decor/decor_NNN.png (every scenery decoration, the four
 * mirror modes side by side) and OUTDIR/decorations.png (contact sheet).
 */
#include "../src/spectrum.c"
#include "png.h"

#define STUB 0x3000
#define DRAW_DECOR 0x7409     /* A=index, L=column, H=row, C=mirror mode 0-3 */
#define DECOR_TABLE 0xC544

static Spectrum S;

static void frames(int n) { for (int i = 0; i < n; i++) spec_run_frame(&S); }
static void tap_key(int row, int bit) { spec_key(&S, row, bit, 1); frames(6); spec_key(&S, row, bit, 0); frames(14); }

/* call a game routine and run until it returns to the stub */
static int call(uint16_t addr)
{
    Z80 *z = &S.cpu;
    z->sp -= 2;
    mem_write(&S, z->sp, STUB & 0xff);
    mem_write(&S, (uint16_t)(z->sp + 1), STUB >> 8);
    z->pc = addr;
    z->halted = 0;
    z->iff1 = z->iff2 = 0;    /* keep the game's interrupt-driven logic out of the way */
    for (long t = 0; t < 20000000; ) {
        if (z->pc == STUB) return 0;
        t += z80_step(z);
    }
    return -1;
}

static void clear_screen(uint8_t attr)
{
    memset(S.ram[5], 0, 6144);
    memset(S.ram[5] + 6144, attr, 768);
    S.port7ffd &= ~8;
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s tap outdir\n", argv[0]); return 2; }
    char err[256], path[600];
    if (spec_load_spellbound_tap(&S, argv[1], err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
    S.rom[STUB] = 0x76; S.rom[STUB + 1] = 0x18; S.rom[STUB + 2] = 0xfd;

    frames(300);
    for (int i = 0; i < 6; i++) tap_key(0, 1);
    tap_key(7, 0);
    frames(150);
    S.port7ffd &= ~7;

    snprintf(path, sizeof path, "%s/decor", argv[2]);
    char cmd[700];
    snprintf(cmd, sizeof cmd, "mkdir -p '%s'", path);
    if (system(cmd)) return 1;

    /* contact sheet: one row per decoration, the four modes side by side
     * (0 = normal, 1 = mirrored, 2 = flipped vertically, 3 = both). Modes 2/3
     * are drawn upwards from row+h, i.e. one character row lower. */
    const int SW = 4 * 76;
    int sheet_h = 0;
    uint32_t *sheet = calloc((size_t)SW * 76 * 90, 4);
    static uint8_t snap[0x10000];
    for (int idx = 45; idx < 128; idx++) {
        uint8_t w = mem_read(&S, DECOR_TABLE + idx * 4), h = mem_read(&S, DECOR_TABLE + idx * 4 + 1);
        if (w < 1 || w > 9 || h < 1 || h > 9) continue;
        int iw = 4 * (w * 8 + 4), ih = h * 8;
        static uint32_t img[4 * 76 * 76];
        for (int i = 0; i < iw * ih; i++) img[i] = 0;
        for (int mode = 0; mode < 4; mode++) {
            int yoff = mode < 2 ? 0 : 8;
            /* run from a pristine copy of RAM each time so draws don't accumulate state */
            for (int a = 0x4000; a < 0x10000; a++) snap[a] = mem_read(&S, a);
            Z80 saved = S.cpu;
            clear_screen(0x07);
            S.cpu.a = (uint8_t)idx;
            S.cpu.l = 2; S.cpu.h = 4;          /* column 2, row 4 */
            S.cpu.c = (uint8_t)mode; S.cpu.b = 0;
            if (call(DRAW_DECOR)) fprintf(stderr, "decor %d mode %d did not return\n", idx, mode);
            spec_render(&S);
            for (int y = 0; y < ih; y++)
                for (int x = 0; x < w * 8; x++)
                    img[y * iw + mode * (w * 8 + 4) + x] = S.fb[(24 + 32 + yoff + y) * SCREEN_W + 32 + 16 + x];
            for (int a = 0x4000; a < 0x10000; a++) mem_write(&S, a, snap[a]);
            S.cpu = saved;
        }
        snprintf(path, sizeof path, "%s/decor/decor_%03d.png", argv[2], idx);
        write_png(path, img, iw, ih, iw);
        for (int y = 0; y < ih; y++)
            for (int x = 0; x < iw; x++)
                sheet[(size_t)(sheet_h + y) * SW + x] = img[y * iw + x];
        sheet_h += ih + 4;
        printf("decor %3d: %dx%d cells\n", idx, w, h);
    }
    for (size_t i = 0; i < (size_t)SW * sheet_h; i++) if (!sheet[i]) sheet[i] = 0xFF282828;
    snprintf(path, sizeof path, "%s/decorations.png", argv[2]);
    write_png(path, sheet, SW, sheet_h, SW);
    return 0;
}
