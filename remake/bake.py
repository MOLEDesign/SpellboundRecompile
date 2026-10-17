#!/usr/bin/env python3
"""Builds the remake's data pack from your own copy of the original tape.

    python3 remake/bake.py path/to/S_BND128.TAP

Steps:
  1. builds and runs tools/bake_remake (the original engine running in the
     emulator) to capture each room's scenery and collision map and the
     memory state at the start of a game;
  2. decodes sprites, font, text, exits and the starting positions of all
     objects and characters straight from the tape data;
  3. writes everything to remake/data/ (PNG + game.json).

Nothing produced here is meant to be committed: it is the original game's
artwork and text, extracted for personal use.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from extract_assets import write_png, PAL  # noqa: E402
from tap_extract import read_tap  # noqa: E402

DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")
NUM_ROOMS = 57
NUM_OBJECTS = 50
CHAR_NAMES = ["GIMBAL", "THOR", "FLORIN", "ORIK", "SAMSUN", "ELRAND", "ROSMAR", "BANSHEE"]


class Mem:
    """CPU view of the 128K memory dump with a chosen bank at C000."""

    def __init__(self, banks, high=0):
        self.banks = banks
        self.high = high

    def __getitem__(self, a):
        a &= 0xFFFF
        if a < 0x4000:
            return 0xFF
        if a < 0x8000:
            return self.banks[5][a - 0x4000]
        if a < 0xC000:
            return self.banks[2][a - 0x8000]
        return self.banks[self.high][a - 0xC000]

    def word(self, a):
        return self[a] | self[a + 1] << 8


class Text:
    """Spellbound's dictionary-compressed text (bank 6)."""

    D1, D2 = 0xE8F9, 0xEC4D

    def __init__(self, mem):
        self.m = mem
        self.cache = {}

    def skip(self, a, n):
        for _ in range(n):
            while self.m[a] != 0:
                a += 1
            a += 1
        return a

    def decode(self, a, depth=0):
        key = (a, depth)
        if key in self.cache:
            return self.cache[key]
        out = []
        p = a
        while depth < 5:
            c = self.m[p]
            p += 1
            if c == 0:
                break
            if c in (0x0D, 0x0E):
                out.append("\n")
            elif c < 0x5B:
                out.append(chr(c))
            else:
                t = c - 0x5B
                base = self.D1
                if t >= 0x64:
                    base, t = self.D2, t - 0x64
                out.append(self.decode(self.skip(base, t), depth + 1))
        s = "".join(out)
        self.cache[key] = s
        return s

    def strings(self, start, end):
        res = {}
        a = start
        while a < end:
            res["%04X" % a] = self.decode(a)
            a = self.skip(a, 1)
        return res


def sprite(mem, gfx, mask, w_bytes, h, colour=(255, 255, 255)):
    """RGBA rows; set pixels in colour, mask-0 pixels black, others clear."""
    rows = []
    for y in range(h):
        row = []
        for bx in range(w_bytes):
            g = mem[gfx + y * w_bytes + bx]
            m = mem[mask + y * w_bytes + bx]
            for b in range(8):
                bit = 0x80 >> b
                if g & bit:
                    row.append(colour + (255,))
                elif not (m & bit):
                    row.append((0, 0, 0, 255))
                else:
                    row.append((0, 0, 0, 0))
        rows.append(row)
    return rows


def screen_rgb(scr):
    rows = []
    for y in range(192):
        off = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
        row = []
        for cx in range(32):
            at = scr[6144 + (y >> 3) * 32 + cx]
            br = 8 if at & 0x40 else 0
            ink, paper = PAL[(at & 7) | br], PAL[((at >> 3) & 7) | br]
            bits = scr[off + cx]
            for b in range(8):
                row.append(ink if bits & (0x80 >> b) else paper)
        rows.append(row)
    return rows


def build_raw(tap):
    exe = os.path.join(ROOT, "tools", "bake_remake")
    src = [os.path.join(ROOT, p) for p in ("tools/bake_remake.c", "src/z80.c", "src/spectrum.c")]
    if not os.path.exists(exe) or any(os.path.getmtime(s) > os.path.getmtime(exe) for s in src):
        cc = os.environ.get("CC", "cc")
        subprocess.check_call([cc, "-O2", "-I" + os.path.join(ROOT, "src"), src[0], src[1], "-o", exe])
    os.makedirs(RAW, exist_ok=True)
    subprocess.check_call([exe, tap, RAW])


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 remake/bake.py S_BND128.TAP")
    tap = sys.argv[1]
    build_raw(tap)
    os.makedirs(os.path.join(DATA, "img"), exist_ok=True)

    dump = open(os.path.join(RAW, "mem_start.bin"), "rb").read()
    banks = [dump[i * 16384:(i + 1) * 16384] for i in range(8)]
    # bank 0 as in the dump is the live game RAM; the TAP gives pristine banks 3/6
    payload = [b[1:-1] for b in read_tap(tap) if b[0] == 0xFF]
    for bank, d in zip([1, 3, 4, 6], payload[2:6]):
        banks[bank] = d
    main_mem = Mem(banks, 0)
    text = Text(Mem(banks, 6))

    # ---- loading screen and title music ---------------------------------------
    write_png(os.path.join(DATA, "img", "loading.png"), 256, 192, screen_rgb(payload[1]))
    os.replace(os.path.join(RAW, "title.wav"), os.path.join(DATA, "title.wav"))

    # ---- text -----------------------------------------------------------
    strings = text.strings(0xC000, 0xE8F9)
    room_names = []
    a = 0xDEB6
    for _ in range(NUM_ROOMS):
        # [length][text]0, or a lone 0 = no new name: the original leaves the
        # previous room's name on screen, so inherit it
        if text.m[a] == 0:
            room_names.append(room_names[-1] if room_names else "")
            a += 1
        else:
            room_names.append(text.decode(a + 1).strip())
            a = text.skip(a, 1)
    obj_names = []
    a = 0xDCD8
    for _ in range(NUM_OBJECTS + 7):
        obj_names.append(text.decode(a).strip())
        a = text.skip(a, 1)

    # ---- rooms ----------------------------------------------------------
    rooms = []
    for r in range(NUM_ROOMS):
        scr = open(os.path.join(RAW, "room_%02d.scr" % r), "rb").read()
        col = open(os.path.join(RAW, "room_%02d.col" % r), "rb").read()
        write_png(os.path.join(DATA, "img", "room_%02d.png" % r), 256, 192, screen_rgb(scr))
        grid = []
        for y in range(24):
            if y < 23:
                grid.append("".join("#" if col[y * 32 + x] else "." for x in range(32)))
            else:
                grid.append("#" * 32)        # floor (60E0..60FE in the original)
        left, right = main_mem[0x982A + r * 2], main_mem[0x982B + r * 2]
        rooms.append({"name": room_names[r], "exits": [None if left == 0xFF else left, None if right == 0xFF else right],
                      "solid": grid})

    # ---- graphics -------------------------------------------------------
    def gfx_entry(i):
        return main_mem.word(0xC544 + i * 4), main_mem.word(0xC546 + i * 4)

    for i in range(1, 45):                                    # 16x16 objects
        g, m = gfx_entry(i)
        write_png(os.path.join(DATA, "img", "obj_%02d.png" % i), 16, 16, sprite(main_mem, g, m, 2, 16))
    for c in range(8):                                        # 16x32 characters
        gi = main_mem[0x62CA + c * 8 + 5]
        g, m = gfx_entry(gi)
        write_png(os.path.join(DATA, "img", "char_%d.png" % c), 16, 32, sprite(main_mem, g, m, 2, 32))
    for f in range(8):                                        # 24x32 knight
        write_png(os.path.join(DATA, "img", "knight_%d.png" % f), 24, 32,
                  sprite(main_mem, 0xF9F4 + f * 96, 0xFCF4 + f * 96, 3, 32))
    font = []
    for y in range(8):
        row = []
        for ch in range(128):
            bits = main_mem[0xB700 + ch * 8 + y]
            row.extend((255, 255, 255, 255) if bits & (0x80 >> b) else (0, 0, 0, 0) for b in range(8))
        font.append(row)
    write_png(os.path.join(DATA, "img", "font.png"), 1024, 8, font)

    # ---- objects and characters -------------------------------------------
    objects = []
    for i in range(NUM_OBJECTS):
        room, x, y = (main_mem[0x635C + i * 3 + k] for k in range(3))
        d = [main_mem[0x9A1D + i * 8 + k] for k in range(8)]
        objects.append({"id": i, "name": obj_names[i], "room": None if room >= NUM_ROOMS else room,
                        "x": x, "y": y, "gfx": d[7], "attr": d[6], "flags": d[0:6]})
    characters = []
    for c in range(8):
        room, x, y = (main_mem[0x6344 + c * 3 + k] for k in range(3))
        rec = [main_mem[0x62CA + c * 8 + k] for k in range(8)]
        holds = [main_mem[0x631C + c * 5 + k] for k in range(5)]
        characters.append({"id": c, "name": CHAR_NAMES[c], "room": None if room >= NUM_ROOMS else room,
                           "x": x, "y": y, "attr": rec[4], "stats": rec[0:4], "holds": [h for h in holds if h]})

    game = {"rooms": rooms, "objects": objects, "characters": characters,
            "start": {"room": main_mem[0x5C95], "x": main_mem[0x630A], "y": main_mem[0x630B]},
            "text": strings}
    with open(os.path.join(DATA, "game.json"), "w") as f:
        json.dump(game, f, indent=1)
    print("data pack written to", DATA)


if __name__ == "__main__":
    main()
