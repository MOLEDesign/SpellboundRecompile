/* ZX Spectrum 128K machine for Spellbound. See spectrum.h. */
#include "spectrum.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CPU_HZ 3546900.0
#define AY_HZ (CPU_HZ / 2.0)
#define FIRST_PIXEL_LINE 63   /* 128K: first line of the 192-line bitmap */
#define TOP_BORDER 24

static const uint32_t palette[16] = {
    0xFF000000, 0xFF0000D7, 0xFFD70000, 0xFFD700D7, 0xFF00D700, 0xFF00D7D7, 0xFFD7D700, 0xFFD7D7D7,
    0xFF000000, 0xFF0000FF, 0xFFFF0000, 0xFFFF00FF, 0xFF00FF00, 0xFF00FFFF, 0xFFFFFF00, 0xFFFFFFFF,
};

/* ---------------- memory ---------------- */

static inline uint8_t *page(Spectrum *s, uint16_t a)
{
    switch (a >> 14) {
    case 0: return s->rom;
    case 1: return s->ram[5];
    case 2: return s->ram[2];
    default: return s->ram[s->port7ffd & 7];
    }
}

static uint8_t mem_read(void *ctx, uint16_t a)
{
    Spectrum *s = ctx;
    return page(s, a)[a & 0x3fff];
}

static void mem_write(void *ctx, uint16_t a, uint8_t v)
{
    Spectrum *s = ctx;
    if (a < 0x4000) return;
    page(s, a)[a & 0x3fff] = v;
}

/* ---------------- AY-3-8912 ---------------- */

static const float ay_vol[16] = {
    0.0f, 0.0106f, 0.0150f, 0.0222f, 0.0320f, 0.0466f, 0.0665f, 0.1039f,
    0.1237f, 0.1986f, 0.2803f, 0.3548f, 0.4702f, 0.6030f, 0.7530f, 1.0f,
};

static void ay_env_restart(AY *ay)
{
    uint8_t shape = ay->reg[13];
    ay->env_att = (shape & 4) ? 0x1f : 0;
    ay->env_step = 0x1f;
    ay->env_hold = 0;
    ay->env_alt = 0;
    ay->env_cnt = 0;
    ay->env_vol = (ay->env_step ^ ay->env_att) >> 1;
}

static void ay_write(AY *ay, uint8_t r, uint8_t v)
{
    static const uint8_t mask[16] = {0xff, 0x0f, 0xff, 0x0f, 0xff, 0x0f, 0x1f, 0xff,
                                     0x1f, 0x1f, 0x1f, 0xff, 0xff, 0x0f, 0xff, 0xff};
    r &= 15;
    ay->reg[r] = v & mask[r];
    if (r == 13) ay_env_restart(ay);
}

/* one tick of the AY at clock/8 */
static void ay_tick(AY *ay)
{
    /* tone output flips every `period` ticks -> f = clock / (16 * period) */
    for (int c = 0; c < 3; c++) {
        uint32_t period = ay->reg[c * 2] | (ay->reg[c * 2 + 1] << 8);
        if (period == 0) period = 1;
        if (++ay->tone_cnt[c] >= period) { ay->tone_cnt[c] = 0; ay->tone_out[c] ^= 1; }
    }
    uint32_t np = ay->reg[6] ? ay->reg[6] : 1;
    if (++ay->noise_cnt >= np * 2) {
        ay->noise_cnt = 0;
        /* 17-bit LFSR */
        uint32_t bit = (ay->noise_lfsr ^ (ay->noise_lfsr >> 3)) & 1;
        ay->noise_lfsr = (ay->noise_lfsr >> 1) | (bit << 16);
        ay->noise_out = ay->noise_lfsr & 1;
    }
    uint32_t ep = ay->reg[11] | (ay->reg[12] << 8);
    if (ep == 0) ep = 1;
    /* 32 half-steps per envelope cycle: one every 8*EP clocks */
    if (++ay->env_cnt >= ep) {
        ay->env_cnt = 0;
        if (!ay->env_hold) {
            ay->env_step--;
            if (ay->env_step < 0) {
                uint8_t shape = ay->reg[13];
                if (!(shape & 8)) { ay->env_hold = 1; ay->env_att = 0; ay->env_step = 0; }
                else {
                    if (shape & 1) {
                        ay->env_hold = 1;
                        if (shape & 2) ay->env_att ^= 0x1f;
                        ay->env_step = 0;
                    } else {
                        if (shape & 2) ay->env_att ^= 0x1f;
                        ay->env_step = 0x1f;
                    }
                }
            }
        }
        ay->env_vol = ((ay->env_step ^ ay->env_att) & 0x1f) >> 1;
    }
}

static float ay_output(AY *ay)
{
    float out = 0;
    uint8_t mix = ay->reg[7];
    for (int c = 0; c < 3; c++) {
        int tone_on = !(mix & (1 << c));
        int noise_on = !(mix & (8 << c));
        int level = (tone_on ? ay->tone_out[c] : 1) & (noise_on ? ay->noise_out : 1);
        if (!level) continue;
        uint8_t v = ay->reg[8 + c];
        out += (v & 0x10) ? ay_vol[ay->env_vol] : ay_vol[v & 15];
    }
    return out;
}

/* ---------------- audio ---------------- */

static void audio_render_to(Spectrum *s, int t)
{
    int target = (int)((long long)t * s->audio_samples / FRAME_T);
    if (target > s->audio_samples) target = s->audio_samples;
    const double ticks_per_sample = AY_HZ / 8.0 / AUDIO_RATE;
    while (s->audio_pos < target) {
        AY *ay = &s->ay;
        ay->frac += ticks_per_sample;
        int n = (int)ay->frac;
        ay->frac -= n;
        float acc = 0;
        for (int i = 0; i < n; i++) { ay_tick(ay); acc += ay_output(ay); }
        float v = n ? acc / n : ay_output(ay);
        v = v * 0.28f + (s->beeper ? 0.25f : 0.0f);
        /* DC blocking high-pass */
        float y = v - s->hp_prev + 0.995f * s->hp_l;
        s->hp_prev = v;
        s->hp_l = y;
        int iv = (int)(y * 28000.0f);
        if (iv > 32767) iv = 32767;
        if (iv < -32768) iv = -32768;
        s->audio[s->audio_pos * 2] = (int16_t)iv;
        s->audio[s->audio_pos * 2 + 1] = (int16_t)iv;
        s->audio_pos++;
    }
}

/* ---------------- ports ---------------- */

static uint8_t port_in(void *ctx, uint16_t port)
{
    Spectrum *s = ctx;
    if (!(port & 1)) {
        uint8_t v = 0xff;
        uint8_t hi = port >> 8;
        for (int r = 0; r < 8; r++)
            if (!(hi & (1 << r))) v &= s->keys[r];
        return v | 0xa0;   /* bits 5,7 high; EAR bit (6) low */
    }
    if ((port & 0xc002) == 0xc000) return s->ay.reg[s->ay.sel & 15];
    if (!(port & 0x20)) return s->kempston;
    return 0xff;
}

static void port_out(void *ctx, uint16_t port, uint8_t v)
{
    Spectrum *s = ctx;
    if (!(port & 1)) {
        uint8_t b = (v >> 4) & 1;
        if (b != s->beeper) { audio_render_to(s, s->frame_t); s->beeper = b; }
        s->border = v & 7;
        int line = s->frame_t / LINE_T;
        if (line < 312) for (int l = line; l < 312; l++) s->line_border[l] = s->border;
    }
    if (!(port & 0x8002)) {
        if (!s->paging_locked) {
            s->port7ffd = v;
            if (v & 0x20) s->paging_locked = 1;
        }
    }
    if ((port & 0xc002) == 0xc000) s->ay.sel = v;
    if ((port & 0xc002) == 0x8000) { audio_render_to(s, s->frame_t); ay_write(&s->ay, s->ay.sel, v); }
}

/* ---------------- synthetic ROM + traps ---------------- */

static void build_rom(Spectrum *s)
{
    memset(s->rom, 0xff, sizeof s->rom);   /* IM2 vector table bytes = 0xFF */
    s->rom[0x0000] = 0xf3;                 /* DI: also the JR offset used by the IM2 trick at 0xFFFF */
    s->rom[0x0001] = 0x18; s->rom[0x0002] = 0xfe; /* reset -> hang */
    /* IM1 handler: bump FRAMES like the real ROM does */
    static const uint8_t im1[] = {0xf5, 0xe5, 0x2a, 0x78, 0x5c, 0x23, 0x22, 0x78, 0x5c, 0xe1, 0xf1, 0xfb, 0xc9};
    memcpy(s->rom + 0x38, im1, sizeof im1);
    /* trap points are executed by the emulator, but leave a RET in case */
    s->rom[0x04c2] = 0xc9;
    s->rom[0x0556] = 0xc9;
    s->rom[0x02bf] = 0xc9;
}

/* SA-BYTES: IX=start, DE=length, A=flag. LD-BYTES: same, carry set = load. */
static void ret(Spectrum *s);
static void trap_tape(Spectrum *s, int save)
{
    Z80 *z = &s->cpu;
    const char *path = s->save_path ? s->save_path : "spellbound.sav";
    int ok = 0;
    if (save) {
        FILE *f = fopen(path, "ab");
        if (f) {
            uint8_t hdr[4] = {z->a, (uint8_t)z->e, (uint8_t)z->d, 0};
            fwrite(hdr, 1, 4, f);
            for (uint16_t i = 0; i < z->de; i++) fputc(mem_read(s, (uint16_t)(z->ix + i)), f);
            fclose(f);
            ok = 1;
        }
    } else {
        /* scan the file for the first block with matching flag and length */
        FILE *f = fopen(path, "rb");
        if (f) {
            uint8_t hdr[4];
            while (fread(hdr, 1, 4, f) == 4) {
                uint16_t len = hdr[1] | hdr[2] << 8;
                if (hdr[0] == z->a && len == z->de) {
                    for (uint16_t i = 0; i < len; i++) {
                        int c = fgetc(f);
                        if (c == EOF) break;
                        if (z->f & 1) mem_write(s, (uint16_t)(z->ix + i), (uint8_t)c);
                    }
                    ok = 1;
                    /* keep the last matching block: later saves win */
                } else {
                    fseek(f, len, SEEK_CUR);
                }
            }
            fclose(f);
        }
    }
    z->ix += z->de;
    z->de = 0;
    z->f = (z->f & ~1) | (ok ? 1 : 0);
    ret(s);
}

/* KEYBOARD (ROM 0x02BF) replacement, called from the game's interrupt
 * handler. Produces the same visible results as the ROM routine: LAST_K
 * (0x5C08) receives the key code and bit 5 of FLAGS (0x5C3B) is set on a
 * new key press, with auto-repeat after REPDEL frames every REPPER frames. */
static const char key_chars[8][5] = {
    {0, 'Z', 'X', 'C', 'V'}, {'A', 'S', 'D', 'F', 'G'}, {'Q', 'W', 'E', 'R', 'T'}, {'1', '2', '3', '4', '5'},
    {'0', '9', '8', '7', '6'}, {'P', 'O', 'I', 'U', 'Y'}, {13, 'L', 'K', 'J', 'H'}, {' ', 0, 'M', 'N', 'B'},
};
static const char sym_chars[8][5] = {
    {0, ':', '`', '?', '/'}, {'~', '|', '\\', '{', '}'}, {0, 0, 0, '<', '>'}, {'!', '@', '#', '$', '%'},
    {'_', ')', '(', '\'', '&'}, {'"', ';', 0, ']', '['}, {13, '=', '+', '-', '^'}, {' ', 0, '.', ',', '*'},
};

static void hle_keyboard(Spectrum *s)
{
    uint8_t *sv = s->ram[5];
    int caps = !(s->keys[0] & 1), sym = !(s->keys[7] & 2);
    int code = 0, count = 0;
    for (int r = 0; r < 8; r++)
        for (int b = 0; b < 5; b++) {
            if ((r == 0 && b == 0) || (r == 7 && b == 1)) continue;
            if (!(s->keys[r] & (1 << b))) {
                count++;
                char c = key_chars[r][b];
                if (sym && sym_chars[r][b]) c = sym_chars[r][b];
                else if (c >= 'A' && c <= 'Z' && !caps && !(sv[0x1c6a] & 8)) c += 32;
                else if (caps && c >= '0' && c <= '9') {
                    static const uint8_t capsnum[10] = {0x0c, 0x07, 0x06, 0x04, 0x05, 0x08, 0x0a, 0x0b, 0x09, 0x0f};
                    c = capsnum[c - '0'];
                }
                code = (uint8_t)c;
            }
        }
    if (count != 1 || !code) { s->kb_last = 0; return; }
    if (code != s->kb_last) {
        s->kb_last = code;
        s->kb_count = sv[0x1c09] ? sv[0x1c09] : 35;   /* REPDEL */
    } else {
        if (--s->kb_count > 0) return;
        s->kb_count = sv[0x1c0a] ? sv[0x1c0a] : 5;    /* REPPER */
    }
    sv[0x1c08] = (uint8_t)code;   /* LAST_K */
    sv[0x1c3b] |= 0x20;           /* FLAGS: new key */
}

static void ret(Spectrum *s)
{
    Z80 *z = &s->cpu;
    z->pc = mem_read(s, z->sp) | mem_read(s, (uint16_t)(z->sp + 1)) << 8;
    z->sp += 2;
}

/* ---------------- core ---------------- */

void spec_init(Spectrum *s)
{
    uint8_t *cov = s->coverage;
    int tr = s->trace_rom, bp = s->break_pc;
    const char *sp = s->save_path;
    memset(s, 0, sizeof *s);
    s->break_pc = bp;
    s->coverage = cov;
    s->trace_rom = tr;
    s->save_path = sp;
    build_rom(s);
    memset(s->keys, 0xff, sizeof s->keys);
    s->port7ffd = 0x10;
    s->audio_samples = (int)(AUDIO_RATE * (double)FRAME_T / CPU_HZ + 0.5);
    s->ay.noise_lfsr = 1;
    z80_reset(&s->cpu);
    s->cpu.ctx = s;
    s->cpu.read = mem_read;
    s->cpu.write = mem_write;
    s->cpu.in = port_in;
    s->cpu.out = port_out;
}

static const uint8_t *tap_blocks(const uint8_t *d, size_t n, const uint8_t **blk, uint16_t *len, int max, int *count)
{
    size_t i = 0;
    *count = 0;
    while (i + 2 <= n && *count < max) {
        uint16_t l = d[i] | d[i + 1] << 8;
        if (i + 2 + l > n) return NULL;
        blk[*count] = d + i + 2;
        len[*count] = l;
        (*count)++;
        i += 2 + l;
    }
    return d;
}

int spec_load_spellbound_tap(Spectrum *s, const char *path, char *err, int errlen)
{
    FILE *f = fopen(path, "rb");
    if (!f) { snprintf(err, errlen, "cannot open %s", path); return -1; }
    static uint8_t buf[256 * 1024];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    const uint8_t *blk[32];
    uint16_t len[32];
    int count;
    if (!tap_blocks(buf, n, blk, len, 32, &count)) { snprintf(err, errlen, "truncated TAP"); return -1; }
    const uint8_t *data[16];
    uint16_t dlen[16];
    int nd = 0;
    for (int i = 0; i < count && nd < 16; i++) {
        if (len[i] < 2 || blk[i][0] != 0xff) continue;
        uint8_t x = 0;
        for (int k = 0; k < len[i]; k++) x ^= blk[i][k];
        if (x) { snprintf(err, errlen, "checksum error in TAP block %d", i); return -1; }
        data[nd] = blk[i] + 1;
        dlen[nd] = len[i] - 2;
        nd++;
    }
    if (nd != 7 || dlen[1] != 6912 || dlen[2] != 16384 || dlen[6] != 39295) {
        snprintf(err, errlen, "this does not look like the Spellbound 128K TAP");
        return -1;
    }
    spec_init(s);
    memcpy(s->ram[5], data[1], 6912);             /* LOAD "" SCREEN$ */
    static const int banks[4] = {1, 3, 4, 6};
    for (int i = 0; i < 4; i++) memcpy(s->ram[banks[i]], data[2 + i], 16384);
    for (int i = 0; i < 39295; i++) mem_write(s, (uint16_t)(26240 + i), data[6][i]);

    /* minimal system variables the game may look at */
    uint8_t *sv = s->ram[5];
    sv[0x1b5c] = 0x10;              /* BANKM (0x5B5C) */
    sv[0x1c3b] = 0x0c;              /* FLAGS */
    sv[0x1c6a] = 0x08;              /* FLAGS2 */
    sv[0x1c8d] = 0x38;              /* ATTR_P */
    sv[0x1c09] = 35;                /* REPDEL */
    sv[0x1c0a] = 5;                 /* REPPER */
    sv[0x1cb2] = 26200 & 0xff; sv[0x1cb3] = 26200 >> 8; /* RAMTOP */

    Z80 *z = &s->cpu;
    z->iy = 0x5c3a;
    z->hl_ = 0x2758;
    z->i = 0x3f;
    z->im = 1;
    z->iff1 = z->iff2 = 1;
    z->sp = 26198;
    z->sp -= 2;                      /* return address of USR -> ROM reset (unused) */
    mem_write(s, z->sp, 0x00); mem_write(s, (uint16_t)(z->sp + 1), 0x00);
    z->pc = 26627;
    z->af = 0x0000;
    z->bc = 26627;
    return 0;
}

void spec_key(Spectrum *s, int row, int bit, int down)
{
    if (down) s->keys[row] &= ~(1 << bit);
    else s->keys[row] |= 1 << bit;
}

void spec_run_frame(Spectrum *s)
{
    Z80 *z = &s->cpu;
    s->audio_pos = 0;
    for (int l = 0; l < 312; l++) s->line_border[l] = s->border;
    s->frame_t = 0;
    while (s->frame_t < FRAME_T) {
        z->irq_line = s->frame_t < 36;
        uint16_t pc = z->pc;
        if (pc == s->break_pc) { s->break_hit = 1; return; }
        if (pc < 0x4000) {
            if (pc == 0x0556) { trap_tape(s, 0); s->frame_t += 100; continue; }
            if (pc == 0x04c2) { trap_tape(s, 1); s->frame_t += 100; continue; }
            if (pc == 0x02bf) { hle_keyboard(s); ret(s); s->frame_t += 600; continue; }
            if (s->trace_rom && pc != 0x38 && !(pc >= 0x39 && pc < 0x45))
                fprintf(stderr, "ROM call at %04X (frame %u, SP=%04X ret=%04X)\n", pc, s->frame, z->sp,
                        mem_read(s, z->sp) | mem_read(s, (uint16_t)(z->sp + 1)) << 8);
        }
        if (s->coverage) {
            int bank = pc >= 0xc000 ? (s->port7ffd & 7) : 0;
            s->coverage[bank * 65536 + pc] = 1;
        }
        s->frame_t += z80_step(z);
    }
    audio_render_to(s, FRAME_T);
    s->frame++;
}

void spec_render_scr(const uint8_t *scr, uint32_t *fb, int stride, int flash)
{
    for (int y = 0; y < 192; y++) {
        int off = ((y & 0xc0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2);
        uint32_t *row = fb + y * stride;
        for (int cx = 0; cx < 32; cx++) {
            uint8_t bits = scr[off + cx];
            uint8_t at = scr[6144 + (y >> 3) * 32 + cx];
            int br = (at & 0x40) ? 8 : 0;
            uint32_t ink = palette[(at & 7) | br], paper = palette[((at >> 3) & 7) | br];
            if ((at & 0x80) && flash) { uint32_t t = ink; ink = paper; paper = t; }
            for (int b = 0; b < 8; b++) row[cx * 8 + b] = (bits & (0x80 >> b)) ? ink : paper;
        }
    }
}

void spec_render(Spectrum *s)
{
    const uint8_t *scr = s->ram[(s->port7ffd & 8) ? 7 : 5];
    for (int y = 0; y < SCREEN_H; y++) {
        int line = FIRST_PIXEL_LINE - TOP_BORDER + y;
        uint32_t c = palette[s->line_border[line < 312 ? line : 311]];
        uint32_t *row = s->fb + y * SCREEN_W;
        for (int x = 0; x < SCREEN_W; x++) row[x] = c;
    }
    spec_render_scr(scr, s->fb + TOP_BORDER * SCREEN_W + 32, SCREEN_W, (s->frame >> 4) & 1);
}
