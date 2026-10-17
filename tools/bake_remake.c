/* Bakes data for the remake by running the original engine once:
 *   OUT/mem_start.bin   8 RAM banks right after "PLAY GAME" (object and
 *                       character tables are initialised by then)
 *   OUT/room_NN.scr     6912-byte screen of each room's scenery, captured
 *                       when enter_room reaches room_finish (7116), i.e.
 *                       before objects, characters and the knight are drawn
 *   OUT/room_NN.col     736-byte collision map (5E00-60DF) at the same point
 *   OUT/title.wav       recording of the title music (AY), 16-bit stereo
 *
 *   cc -O2 -Isrc tools/bake_remake.c src/z80.c -o tools/bake_remake
 *   tools/bake_remake S_BND128.TAP remake/data/raw
 */
#include "../src/spectrum.c"

#define STUB 0x3000
#define ENTER_ROOM 0x6FA6
#define ROOM_FINISH 0x7116
#define ROOM_TIMER 0x62C2
#define NUM_ROOMS 57

static Spectrum S;

static void frames(int n) { for (int i = 0; i < n; i++) spec_run_frame(&S); }
static void tap_key(int row, int bit) { spec_key(&S, row, bit, 1); frames(6); spec_key(&S, row, bit, 0); frames(14); }

/* run the title screen for a while and record the AY music */
static int record_title(const char *tap, const char *dir)
{
    char err[256], path[600];
    if (spec_load_spellbound_tap(&S, tap, err, sizeof err)) { fprintf(stderr, "%s\n", err); return -1; }
    snprintf(path, sizeof path, "%s/title.wav", dir);
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return -1; }
    uint8_t hdr[44] = {0};
    fwrite(hdr, 1, 44, f);
    uint32_t bytes = 0;
    for (int i = 0; i < 3400; i++) {
        spec_run_frame(&S);
        if (i >= 30) { fwrite(S.audio, 4, S.audio_pos, f); bytes += S.audio_pos * 4; }
    }
    uint32_t v[] = {36 + bytes, AUDIO_RATE, AUDIO_RATE * 4, bytes};
    memcpy(hdr, "RIFF", 4); memcpy(hdr + 4, &v[0], 4); memcpy(hdr + 8, "WAVEfmt ", 8);
    hdr[16] = 16; hdr[20] = 1; hdr[22] = 2;
    memcpy(hdr + 24, &v[1], 4); memcpy(hdr + 28, &v[2], 4);
    hdr[32] = 4; hdr[34] = 16;
    memcpy(hdr + 36, "data", 4); memcpy(hdr + 40, &v[3], 4);
    fseek(f, 0, SEEK_SET);
    fwrite(hdr, 1, 44, f);
    fclose(f);
    return 0;
}

static int save(const char *dir, const char *name, const void *p, size_t n)
{
    char path[600];
    snprintf(path, sizeof path, "%s/%s", dir, name);
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return -1; }
    fwrite(p, 1, n, f);
    fclose(f);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s tap outdir\n", argv[0]); return 2; }
    char err[256], name[64];
    S.break_pc = -1;
    if (record_title(argv[1], argv[2])) return 1;
    if (spec_load_spellbound_tap(&S, argv[1], err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
    S.rom[STUB] = 0x76; S.rom[STUB + 1] = 0x18; S.rom[STUB + 2] = 0xfd;

    frames(300);
    for (int i = 0; i < 6; i++) tap_key(0, 1);   /* Z x6 -> PLAY GAME */
    tap_key(7, 0);                               /* SPACE */
    frames(150);
    if (save(argv[2], "mem_start.bin", S.ram, sizeof S.ram)) return 1;

    Z80 *z = &S.cpu;
    for (int r = 0; r < NUM_ROOMS; r++) {
        S.port7ffd &= ~7;
        mem_write(&S, ROOM_TIMER, 0x3d);
        z->sp -= 2;
        mem_write(&S, z->sp, STUB & 0xff);
        mem_write(&S, (uint16_t)(z->sp + 1), STUB >> 8);
        z->a = (uint8_t)r;
        z->pc = ENTER_ROOM;
        z->halted = 0;
        S.break_pc = ROOM_FINISH;
        S.break_hit = 0;
        for (int f = 0; f < 300 && !S.break_hit; f++) spec_run_frame(&S);
        S.break_pc = -1;
        if (!S.break_hit) { fprintf(stderr, "room %d: never reached room_finish\n", r); return 1; }
        snprintf(name, sizeof name, "room_%02d.scr", r);
        save(argv[2], name, S.ram[5], 6912);
        snprintf(name, sizeof name, "room_%02d.col", r);
        save(argv[2], name, S.ram[5] + 0x1e00, 0x2e0);
        z->pc = STUB;
        frames(2);
    }
    printf("baked %d rooms into %s\n", NUM_ROOMS, argv[2]);
    return 0;
}
