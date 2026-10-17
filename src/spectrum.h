/* Minimal ZX Spectrum 128K machine: just what Spellbound needs.
 * Memory paging (0x7FFD), ULA video (normal/shadow screen, border),
 * beeper, AY-3-8912, keyboard matrix and Kempston joystick.
 * The Sinclair/Amstrad ROM is NOT used: a tiny synthetic ROM provides
 * the IM2 vector bytes the game relies on, and tape LOAD/SAVE calls are
 * trapped and redirected to a file (used for SAVE/LOAD game position). */
#ifndef SPECTRUM_H
#define SPECTRUM_H
#include <stdint.h>
#include "z80.h"

#define SCREEN_W 320
#define SCREEN_H 240
#define FRAME_T 70908
#define LINE_T 228
#define AUDIO_RATE 44100
#define AUDIO_MAX_FRAME 1024

typedef struct {
    uint8_t reg[16];
    uint8_t sel;
    uint32_t tone_cnt[3];
    uint8_t tone_out[3];
    uint32_t noise_cnt, noise_lfsr;
    uint8_t noise_out;
    uint32_t env_cnt;
    int env_step;     /* 0..31 */
    uint8_t env_hold, env_alt, env_att;
    uint8_t env_vol;
    double frac;      /* fractional AY ticks carried between samples */
} AY;

typedef struct Spectrum {
    Z80 cpu;
    uint8_t rom[0x4000];
    uint8_t ram[8][0x4000];
    uint8_t port7ffd;
    uint8_t paging_locked;
    uint8_t border;
    uint8_t line_border[312];
    uint8_t beeper;
    uint8_t keys[8];      /* active-low matrix rows, 0xFF = nothing pressed */
    uint8_t kempston;     /* active-high */
    uint32_t frame;
    int frame_t;          /* T-state within the current frame */
    int kb_last, kb_count; /* HLE keyboard repeat state */

    /* audio */
    int16_t audio[AUDIO_MAX_FRAME * 2];
    int audio_pos;        /* samples produced so far this frame */
    int audio_samples;    /* samples per frame */
    AY ay;
    float hp_l, hp_prev;  /* DC blocker */

    /* diagnostics */
    uint8_t *coverage;    /* optional: 64K*8 bytes, executed-address map per C000 bank */
    int trace_rom;
    const char *save_path;

    uint32_t fb[SCREEN_W * SCREEN_H]; /* 0xAARRGGBB */
} Spectrum;

void spec_init(Spectrum *s);
/* Load the Spellbound 128K TAP and set the machine up as if its BASIC
 * loader had just executed RANDOMIZE USR 26627. Returns 0 on success. */
int spec_load_spellbound_tap(Spectrum *s, const char *path, char *err, int errlen);
void spec_run_frame(Spectrum *s);
void spec_render(Spectrum *s);

/* keyboard: key indices are row*5+bit using the ZX layout */
void spec_key(Spectrum *s, int row, int bit, int down);
enum { KEMP_RIGHT = 1, KEMP_LEFT = 2, KEMP_DOWN = 4, KEMP_UP = 8, KEMP_FIRE = 16 };

/* raw 6912-byte SCREEN$ to framebuffer (used for the loading screen) */
void spec_render_scr(const uint8_t *scr, uint32_t *fb, int stride, int flash);

#endif
