/* Room mapper: boots the game into play, then calls the game's own
 * "enter room" routine (sub_6FA6, A = room number) for every room and
 * saves a PNG of each (OUTDIR/room_NN.png), plus OUTDIR/all_rooms.png.
 *
 *   cc -O2 -Isrc tools/mapper.c src/z80.c -o mapper
 *   ./mapper S_BND128.TAP OUTDIR [first last]
 */
#include "../src/spectrum.c"
#include "png.h"

#define STUB 0x3000            /* unused synthetic-ROM address used as return target */
#define ENTER_ROOM 0x6FA6
#define ROOM_TIMER 0x62C2      /* must be non-zero or the routine shows a message instead */

static Spectrum S;

static void frames(int n) { for (int i = 0; i < n; i++) spec_run_frame(&S); }
static void tap_key(int row, int bit) { spec_key(&S, row, bit, 1); frames(6); spec_key(&S, row, bit, 0); frames(14); }

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s tap outdir [first last]\n", argv[0]); return 2; }
    int first = argc > 3 ? atoi(argv[3]) : 0, last = argc > 4 ? atoi(argv[4]) : 56;   /* 57 rooms: 9120 bytes of layouts / 160 */
    S.break_pc = -1;
    char err[256], path[512];
    if (spec_load_spellbound_tap(&S, argv[1], err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
    S.rom[STUB] = 0x76;                       /* HALT; JR STUB */
    S.rom[STUB + 1] = 0x18; S.rom[STUB + 2] = 0xfd;

    /* menu -> PLAY GAME */
    frames(300);
    for (int i = 0; i < 6; i++) tap_key(0, 1);  /* Z */
    tap_key(7, 0);                              /* SPACE */
    frames(150);

    int n = last - first + 1, cols = 8, rows = (n + cols - 1) / cols;
    const int cw = 256, ch = 168;               /* crop: room name line + 16x10 block playfield */
    uint32_t *sheet = calloc((size_t)cols * cw * rows * ch, 4);
    for (int r = first; r <= last; r++) {
        Z80 *z = &S.cpu;
        S.port7ffd = (S.port7ffd & ~7) | 0;     /* bank 0 at C000 as in the main loop */
        mem_write(&S, ROOM_TIMER, 0x3d);
        z->sp -= 2;
        mem_write(&S, z->sp, STUB & 0xff);
        mem_write(&S, (uint16_t)(z->sp + 1), STUB >> 8);
        z->a = (uint8_t)r;
        z->pc = ENTER_ROOM;
        z->halted = 0;
        int f;
        for (f = 0; f < 200 && !(z->pc >= STUB && z->pc <= STUB + 2); f++) spec_run_frame(&S);
        spec_run_frame(&S);
        spec_render(&S);
        snprintf(path, sizeof path, "%s/room_%02d.png", argv[2], r);
        write_png(path, S.fb + (24 + 32) * SCREEN_W + 32, 256, 168, SCREEN_W);
        printf("room %2d: %s (%d frames)\n", r, f < 200 ? "ok" : "TIMEOUT", f);
        int i = r - first, ox = (i % cols) * cw, oy = (i / cols) * ch;
        for (int y = 0; y < ch; y++)
            memcpy(sheet + (size_t)(oy + y) * cols * cw + ox, S.fb + (24 + 32 + y) * SCREEN_W + 32, cw * 4);
        /* drop back into the game's main loop state for the next room */
        z->pc = STUB;
    }
    snprintf(path, sizeof path, "%s/all_rooms.png", argv[2]);
    write_png(path, sheet, cols * cw, rows * ch, cols * cw);
    return 0;
}
