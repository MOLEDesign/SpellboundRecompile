/* Spellbound for macOS (and Linux) - SDL2 front end.
 *
 *   spellbound [options] [S_BND128.TAP]
 *
 * Options:
 *   --scale N          window scale (default 3)
 *   --fullscreen
 *   --no-loading       skip the loading-screen pause
 *   --save FILE        file used by the in-game SAVE/LOAD option
 * Headless / tooling:
 *   --headless         no window or audio
 *   --frames N         stop after N frames
 *   --shot F:FILE      write a BMP of frame F (repeatable)
 *   --key F:KEYS:N     press KEYS (e.g. "space", "m", "a+m") at frame F for N frames
 *   --coverage FILE    dump executed addresses (for tools/z80dis.py)
 *   --trace-rom        log calls into the (absent) ROM
 *   --wav FILE         record the audio output (16-bit stereo 44.1kHz)
 */
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "spectrum.h"

/* ZX key positions: row (0..7) and bit (0..4) */
typedef struct { const char *name; int row, bit; } ZXKey;
static const ZXKey zxkeys[] = {
    {"shift", 0, 0}, {"z", 0, 1}, {"x", 0, 2}, {"c", 0, 3}, {"v", 0, 4},
    {"a", 1, 0}, {"s", 1, 1}, {"d", 1, 2}, {"f", 1, 3}, {"g", 1, 4},
    {"q", 2, 0}, {"w", 2, 1}, {"e", 2, 2}, {"r", 2, 3}, {"t", 2, 4},
    {"1", 3, 0}, {"2", 3, 1}, {"3", 3, 2}, {"4", 3, 3}, {"5", 3, 4},
    {"0", 4, 0}, {"9", 4, 1}, {"8", 4, 2}, {"7", 4, 3}, {"6", 4, 4},
    {"p", 5, 0}, {"o", 5, 1}, {"i", 5, 2}, {"u", 5, 3}, {"y", 5, 4},
    {"enter", 6, 0}, {"l", 6, 1}, {"k", 6, 2}, {"j", 6, 3}, {"h", 6, 4},
    {"space", 7, 0}, {"sym", 7, 1}, {"m", 7, 2}, {"n", 7, 3}, {"b", 7, 4},
};

static const ZXKey *find_key(const char *name)
{
    for (size_t i = 0; i < sizeof zxkeys / sizeof zxkeys[0]; i++)
        if (!strcmp(zxkeys[i].name, name)) return &zxkeys[i];
    return NULL;
}

static void press_named(Spectrum *s, const char *names, int down)
{
    char buf[64];
    snprintf(buf, sizeof buf, "%s", names);
    for (char *tok = strtok(buf, "+"); tok; tok = strtok(NULL, "+")) {
        if (!strcmp(tok, "kleft")) { if (down) s->kempston |= KEMP_LEFT; else s->kempston &= ~KEMP_LEFT; continue; }
        if (!strcmp(tok, "kright")) { if (down) s->kempston |= KEMP_RIGHT; else s->kempston &= ~KEMP_RIGHT; continue; }
        if (!strcmp(tok, "kup")) { if (down) s->kempston |= KEMP_UP; else s->kempston &= ~KEMP_UP; continue; }
        if (!strcmp(tok, "kdown")) { if (down) s->kempston |= KEMP_DOWN; else s->kempston &= ~KEMP_DOWN; continue; }
        if (!strcmp(tok, "kfire")) { if (down) s->kempston |= KEMP_FIRE; else s->kempston &= ~KEMP_FIRE; continue; }
        const ZXKey *k = find_key(tok);
        if (k) spec_key(s, k->row, k->bit, down);
        else fprintf(stderr, "unknown key '%s'\n", tok);
    }
}

static int write_bmp(const char *path, const uint32_t *px, int w, int h)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    uint32_t size = 54 + w * h * 3;
    uint8_t hdr[54] = {'B', 'M'};
    hdr[2] = size; hdr[3] = size >> 8; hdr[4] = size >> 16; hdr[5] = size >> 24;
    hdr[10] = 54; hdr[14] = 40;
    hdr[18] = w; hdr[19] = w >> 8; hdr[22] = h; hdr[23] = h >> 8;
    hdr[26] = 1; hdr[28] = 24;
    fwrite(hdr, 1, 54, f);
    for (int y = h - 1; y >= 0; y--)
        for (int x = 0; x < w; x++) {
            uint32_t c = px[y * w + x];
            uint8_t bgr[3] = {c & 0xff, (c >> 8) & 0xff, (c >> 16) & 0xff};
            fwrite(bgr, 1, 3, f);
        }
    fclose(f);
    return 0;
}

/* host keyboard -> ZX matrix. Arrow keys drive the game's controls
 * (N/M = left/right, A = up/jump, Z = down) and Kempston at once. */
static void host_key(Spectrum *s, SDL_Keycode k, int down)
{
    char name[16] = "";
    switch (k) {
    case SDLK_LEFT: press_named(s, "n+kleft", down); return;
    case SDLK_RIGHT: press_named(s, "m+kright", down); return;
    case SDLK_UP: press_named(s, "a+kup", down); return;
    case SDLK_DOWN: press_named(s, "z+kdown", down); return;
    case SDLK_RETURN: strcpy(name, "enter"); break;
    case SDLK_SPACE: strcpy(name, "space"); break;
    case SDLK_LSHIFT: strcpy(name, "shift"); break;
    case SDLK_RSHIFT: strcpy(name, "sym"); break;
    case SDLK_LCTRL: case SDLK_RCTRL: strcpy(name, "sym"); break;
    case SDLK_BACKSPACE: press_named(s, "shift+0", down); return;
    case SDLK_ESCAPE: press_named(s, "shift+space", down); return; /* BREAK */
    default:
        if ((k >= SDLK_a && k <= SDLK_z) || (k >= SDLK_0 && k <= SDLK_9)) { name[0] = (char)k; name[1] = 0; }
        break;
    }
    if (name[0]) press_named(s, name, down);
}

#define MAX_EVENTS 256
typedef struct { int frame, len; char keys[32]; } KeyEvent;
typedef struct { int frame; char path[256]; } Shot;

int main(int argc, char **argv)
{
    const char *tap = NULL;
    int scale = 3, fullscreen = 0, headless = 0, frames = -1, no_loading = 0;
    const char *coverage_path = NULL;
    FILE *wav = NULL;
    uint32_t wav_bytes = 0;
    KeyEvent kev[MAX_EVENTS]; int nkev = 0;
    Shot shots[MAX_EVENTS]; int nshots = 0;
    static Spectrum spec;
    Spectrum *s = &spec;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "--scale") && i + 1 < argc) scale = atoi(argv[++i]);
        else if (!strcmp(a, "--fullscreen")) fullscreen = 1;
        else if (!strcmp(a, "--headless")) headless = 1;
        else if (!strcmp(a, "--no-loading")) no_loading = 1;
        else if (!strcmp(a, "--frames") && i + 1 < argc) frames = atoi(argv[++i]);
        else if (!strcmp(a, "--save") && i + 1 < argc) s->save_path = argv[++i];
        else if (!strcmp(a, "--trace-rom")) s->trace_rom = 1;
        else if (!strcmp(a, "--coverage") && i + 1 < argc) coverage_path = argv[++i];
        else if (!strcmp(a, "--wav") && i + 1 < argc) {
            if (!(wav = fopen(argv[++i], "wb"))) { perror(argv[i]); return 1; }
            static const uint8_t blank[44];
            fwrite(blank, 1, 44, wav);
        }
        else if (!strcmp(a, "--shot") && i + 1 < argc && nshots < MAX_EVENTS) {
            Shot *sh = &shots[nshots++];
            if (sscanf(argv[++i], "%d:%255s", &sh->frame, sh->path) != 2) { fprintf(stderr, "bad --shot\n"); return 2; }
        } else if (!strcmp(a, "--key") && i + 1 < argc && nkev < MAX_EVENTS) {
            KeyEvent *e = &kev[nkev++];
            e->len = 5;
            if (sscanf(argv[++i], "%d:%31[^:]:%d", &e->frame, e->keys, &e->len) < 2) { fprintf(stderr, "bad --key\n"); return 2; }
        } else if (a[0] == '-') { fprintf(stderr, "unknown option %s\n", a); return 2; }
        else tap = a;
    }

    /* default TAP locations: argument, next to the executable, app bundle Resources, cwd */
    char pathbuf[1024];
    if (!tap) {
        char *base = SDL_GetBasePath();
        const char *cands[] = {"S_BND128.TAP", "original/S_BND128.TAP", "../Resources/S_BND128.TAP", NULL};
        for (int i = 0; cands[i] && !tap; i++) {
            snprintf(pathbuf, sizeof pathbuf, "%s%s", base ? base : "", cands[i]);
            FILE *f = fopen(pathbuf, "rb");
            if (f) { fclose(f); tap = pathbuf; }
            else {
                f = fopen(cands[i], "rb");
                if (f) { fclose(f); tap = cands[i]; }
            }
        }
        SDL_free(base);
    }
    if (!tap) {
        fprintf(stderr, "usage: %s [options] S_BND128.TAP\n(put S_BND128.TAP next to the program or pass its path)\n", argv[0]);
        return 2;
    }

    if (coverage_path) s->coverage = calloc(8, 65536);
    char err[256];
    if (spec_load_spellbound_tap(s, tap, err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }

    SDL_Window *win = NULL;
    SDL_Renderer *ren = NULL;
    SDL_Texture *tex = NULL;
    SDL_AudioDeviceID dev = 0;
    SDL_GameController *pad = NULL;

    if (!headless) {
        if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER) < 0) {
            fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
            return 1;
        }
        SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");
        win = SDL_CreateWindow("Spellbound", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                               SCREEN_W * scale, SCREEN_H * scale,
                               SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI | (fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0));
        ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
        if (!ren) ren = SDL_CreateRenderer(win, -1, 0);
        SDL_RenderSetLogicalSize(ren, SCREEN_W, SCREEN_H);
        tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, SCREEN_W, SCREEN_H);
        SDL_AudioSpec want = {0}, have;
        want.freq = AUDIO_RATE;
        want.format = AUDIO_S16SYS;
        want.channels = 2;
        want.samples = 1024;
        dev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
        if (dev) SDL_PauseAudioDevice(dev, 0);
        else fprintf(stderr, "no audio: %s\n", SDL_GetError());
        for (int i = 0; i < SDL_NumJoysticks(); i++)
            if (SDL_IsGameController(i) && (pad = SDL_GameControllerOpen(i))) break;
    }

    /* show the loading screen for a moment, as the tape would have */
    int loading_frames = (headless || no_loading) ? 0 : 150;

    int running = 1, paused = 0;
    uint64_t freq = SDL_GetPerformanceFrequency();
    uint64_t next = SDL_GetPerformanceCounter();
    const double frame_secs = (double)FRAME_T / 3546900.0;
    int f = 0;
    while (running) {
        if (!headless) {
            SDL_Event ev;
            while (SDL_PollEvent(&ev)) {
                switch (ev.type) {
                case SDL_QUIT: running = 0; break;
                case SDL_KEYDOWN:
                case SDL_KEYUP:
                    if (ev.key.repeat) break;
                    if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_F11) {
                        fullscreen = !fullscreen;
                        SDL_SetWindowFullscreen(win, fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
                        break;
                    }
                    if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_F1) { paused = !paused; break; }
                    if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_F12) {
                        char name[64];
                        snprintf(name, sizeof name, "spellbound-%05d.bmp", f);
                        write_bmp(name, s->fb, SCREEN_W, SCREEN_H);
                        break;
                    }
                    if (ev.key.keysym.sym == SDLK_q && (ev.key.keysym.mod & KMOD_GUI)) { running = 0; break; }
                    host_key(s, ev.key.keysym.sym, ev.type == SDL_KEYDOWN);
                    break;
                case SDL_CONTROLLERBUTTONDOWN:
                case SDL_CONTROLLERBUTTONUP: {
                    int d = ev.type == SDL_CONTROLLERBUTTONDOWN;
                    switch (ev.cbutton.button) {
                    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: press_named(s, "n+kleft", d); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: press_named(s, "m+kright", d); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_UP: press_named(s, "a+kup", d); break;
                    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: press_named(s, "z+kdown", d); break;
                    case SDL_CONTROLLER_BUTTON_A: press_named(s, "space+kfire", d); break;
                    case SDL_CONTROLLER_BUTTON_B: press_named(s, "a+kup", d); break;
                    case SDL_CONTROLLER_BUTTON_START: press_named(s, "space", d); break;
                    case SDL_CONTROLLER_BUTTON_BACK: press_named(s, "shift+space", d); break;
                    }
                    break;
                }
                case SDL_CONTROLLERDEVICEADDED:
                    if (!pad) pad = SDL_GameControllerOpen(ev.cdevice.which);
                    break;
                }
            }
        }

        for (int i = 0; i < nkev; i++) {
            if (kev[i].frame == f) press_named(s, kev[i].keys, 1);
            if (kev[i].frame + kev[i].len == f) press_named(s, kev[i].keys, 0);
        }

        if (loading_frames > 0) {
            loading_frames--;
            uint32_t c = 0xFF000000;
            for (int i = 0; i < SCREEN_W * SCREEN_H; i++) s->fb[i] = c;
            spec_render_scr(s->ram[5], s->fb + 24 * SCREEN_W + 32, SCREEN_W, 0);
        } else if (!paused) {
            spec_run_frame(s);
            spec_render(s);
            if (wav) { fwrite(s->audio, 4, s->audio_pos, wav); wav_bytes += s->audio_pos * 4; }
            if (dev) {
                /* keep roughly 3 frames queued; drop or pad to stay in sync */
                uint32_t queued = SDL_GetQueuedAudioSize(dev);
                if (queued < (uint32_t)(s->audio_samples * 4 * 8))
                    SDL_QueueAudio(dev, s->audio, s->audio_pos * 4);
            }
        }

        for (int i = 0; i < nshots; i++)
            if (shots[i].frame == f) {
                if (write_bmp(shots[i].path, s->fb, SCREEN_W, SCREEN_H)) perror(shots[i].path);
                else if (headless) printf("frame %d -> %s\n", f, shots[i].path);
            }

        if (!headless) {
            SDL_UpdateTexture(tex, NULL, s->fb, SCREEN_W * 4);
            SDL_RenderClear(ren);
            SDL_RenderCopy(ren, tex, NULL, NULL);
            SDL_RenderPresent(ren);
            /* pace at the real 50.08 Hz regardless of display refresh */
            next += (uint64_t)(frame_secs * freq);
            uint64_t now = SDL_GetPerformanceCounter();
            if (now < next) SDL_Delay((uint32_t)((next - now) * 1000 / freq));
            else if (now - next > freq / 4) next = now;
        }
        f++;
        if (frames >= 0 && f >= frames) running = 0;
    }

    if (wav) {
        uint8_t h[44] = {'R', 'I', 'F', 'F', 0, 0, 0, 0, 'W', 'A', 'V', 'E', 'f', 'm', 't', ' ', 16, 0, 0, 0, 1, 0, 2, 0};
        uint32_t v[] = {36 + wav_bytes, AUDIO_RATE, AUDIO_RATE * 4, wav_bytes};
        memcpy(h + 4, &v[0], 4);
        memcpy(h + 24, &v[1], 4);
        memcpy(h + 28, &v[2], 4);
        h[32] = 4; h[34] = 16;
        memcpy(h + 36, "data", 4);
        memcpy(h + 40, &v[3], 4);
        fseek(wav, 0, SEEK_SET);
        fwrite(h, 1, 44, wav);
        fclose(wav);
    }
    if (coverage_path) {
        FILE *cf = fopen(coverage_path, "wb");
        if (cf) { fwrite(s->coverage, 1, 8 * 65536, cf); fclose(cf); }
    }
    if (!headless) {
        if (pad) SDL_GameControllerClose(pad);
        if (dev) SDL_CloseAudioDevice(dev);
        SDL_DestroyTexture(tex);
        SDL_DestroyRenderer(ren);
        SDL_DestroyWindow(win);
        SDL_Quit();
    }
    return 0;
}
