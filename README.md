# Spellbound (ZX Spectrum 128K) on macOS

A personal-use project to take apart **Spellbound** (Mastertronic / M.A.D.,
David Jones, 1985–86, the 128K version with AY music), pull out its
assets, and play it natively on a Mac.

The original Z80 program runs unchanged inside a small purpose-built
machine written in C. It covers only what this game needs: a Z80 core,
128K memory paging, the ULA screen, AY sound, keyboard and joystick.
No Sinclair/Amstrad ROM is used. The game's only ROM call (the keyboard
scanner) is reimplemented in C.

> The game itself is **not** in this repository. Put your own copy of
> `S_BND128.TAP` in `original/` (or next to the program). `.gitignore` keeps
> the TAP and everything extracted from it out of git.

## Two ways to play

1. **The remake** (`remake/`): a from-scratch Python/pygame-ce version that
   reuses the original rooms, sprites, text and music, with new game code.
   See [remake/README.md](remake/README.md). Quick start:
   `pip3 install pygame-ce && make remake`
2. **The original, running natively** (`src/`): the untouched Z80 program in
   a small built-in 128K Spectrum machine, described below.

## Play the original on macOS

```sh
brew install sdl2
make
./spellbound original/S_BND128.TAP
```

Or build a double-clickable app with the TAP bundled inside:

```sh
make app            # creates Spellbound.app (uses original/S_BND128.TAP)
open Spellbound.app
```

(`brew install dylibbundler` first if you want SDL2 copied into the app so it
runs on a Mac without Homebrew.)

### Controls

| Mac key            | Game                                      |
|--------------------|-------------------------------------------|
| ← / →              | walk left / right (N / M)                 |
| ↑                  | jump, menu pointer up (A)                 |
| ↓                  | menu pointer down (Z)                     |
| Space              | open command menu / choose option         |
| Esc                | BREAK (back to main menu)                 |
| any letter/digit   | the same Spectrum key                     |
| F1                 | pause                                     |
| F11                | toggle full screen                        |
| F12                | save a screenshot (BMP)                   |
| ⌘Q                 | quit                                      |

Game controllers work too: D-pad to move, A to fire/select, B to jump.
The arrow keys drive the Kempston joystick as well, so you can also choose
"Kempston joystick" in the game's menu.

Options: `--scale N`, `--fullscreen`, `--no-loading` (skip the loading
screen pause), `--save FILE`.

## Assets and disassembly

```sh
make extract   # -> extracted/ (raw memory images) and assets/ (PNG, WAV, maps)
make disasm    # -> disasm/spellbound.asm, disasm/bank4_music.asm
```

`assets/` then contains:

| file                         | what                                                         |
|------------------------------|--------------------------------------------------------------|
| `loading_screen.png`         | the SCREEN$ shown while loading                              |
| `font.png`                   | 128-glyph font (window frame pieces + text)                  |
| `tiles.png`, `blocks.png`    | 8×8 scenery tiles and the 16×16 blocks built from them       |
| `decorations.png`, `decor/`  | every scenery picture (trees, axes, portraits…), 4 mirror modes |
| `knight.png`                 | Magic Knight's 8 animation frames (with mask as transparency)|
| `rooms/room_NN.png`          | all 57 rooms with their objects, drawn by the game's own code|
| `rooms/all_rooms.png`        | contact sheet of all rooms                                   |
| `rooms/room_NN.txt`          | raw 16×10 block layout of each room                          |
| `music/title_theme.wav`      | AY recording of the title music                              |
| `data/*.json`                | block definitions, decoration table                          |

See [docs/ANALYSIS.md](docs/ANALYSIS.md) for the memory map, data formats and
how the game works.

## Layout

```
src/z80.c, z80.h        Z80 CPU (passes ZEXDOC and ZEXALL)
src/spectrum.c, .h      128K machine: paging, video, AY, beeper, input, ROM traps
src/main.c              SDL2 front end + headless test/tool mode
tools/tap_extract.py    TAP -> raw memory images
tools/extract_assets.py static graphics -> PNG (no dependencies)
tools/mapper.c          renders every room using the game's own enter_room routine
tools/asset_render.c    renders every decoration using the game's own blitter
tools/z80dis.py         tracing disassembler (with coverage + labels)
tools/labels.txt        names of the routines and tables identified so far
tools/trace_writes.c    analysis helper: who writes to the screen
tests/zextest.c         CP/M harness for the ZEXDOC/ZEXALL CPU tests
```

## Testing

```sh
make zextest && ./zextest zexdoc.com     # Z80 instruction exerciser
./spellbound --headless --frames 600 --shot 599:menu.bmp original/S_BND128.TAP
```

Headless mode can script key presses (`--key FRAME:KEYS:LEN`, e.g.
`--key 700:m:200`) and save screenshots, memory dumps, audio and code
coverage, which is how the tools above drive the game.
