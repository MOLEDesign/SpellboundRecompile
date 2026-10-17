#!/usr/bin/env python3
"""Extract Spellbound graphics into PNG files (no third-party modules).

    python3 tools/extract_assets.py extracted --out assets

Input is the directory written by tools/tap_extract.py. Produces:
    loading_screen.png    the SCREEN$ shown while the game loads
    font.png              128-glyph text font (0xB700, codes 0x00-0x7F)
    tiles.png             8x8 scenery tiles (0xBB00)
    blocks.png            16x16 scenery blocks: 4 tiles + attribute (bank 3, 0xE3A0)
    knight.png            Magic Knight sprite frames, 24x32 (0xF9F4) with mask (0xFCF4)
    rooms/room_NN.txt     160-byte block layout of each room as a 16x10 grid
    data/*.json           block definitions, decoration table
Scale factor for the PNGs is 1 (native); upscale in any viewer.
"""
import argparse
import json
import os
import struct
import zlib

PAL = [(0, 0, 0), (0, 0, 0xD7), (0xD7, 0, 0), (0xD7, 0, 0xD7), (0, 0xD7, 0), (0, 0xD7, 0xD7), (0xD7, 0xD7, 0), (0xD7, 0xD7, 0xD7),
       (0, 0, 0), (0, 0, 0xFF), (0xFF, 0, 0), (0xFF, 0, 0xFF), (0, 0xFF, 0), (0, 0xFF, 0xFF), (0xFF, 0xFF, 0), (0xFF, 0xFF, 0xFF)]

FONT = 0xB700
TILES = 0xBB00
NUM_TILES = 92
BLOCK_DEFS = 0x23A0      # offset inside bank 3 (0xE3A0 when paged at 0xC000)
NUM_ROOMS = 57
KNIGHT_GFX = 0xF9F4
KNIGHT_MASK = 0xFCF4
DECOR_TABLE = 0xC544


def write_png(path, w, h, pixels):
    """pixels: list of rows of (r,g,b[,a]) tuples."""
    alpha = len(pixels[0][0]) == 4
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for px in row:
            raw.extend(px)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


def canvas(w, h, c=(0, 0, 0)):
    return [[c] * w for _ in range(h)]


def blit_glyph(img, x0, y0, rows, ink, paper):
    for y, bits in enumerate(rows):
        for x in range(8):
            img[y0 + y][x0 + x] = ink if bits & (0x80 >> x) else paper


def attr_colours(at):
    br = 8 if at & 0x40 else 0
    return PAL[(at & 7) | br], PAL[((at >> 3) & 7) | br]


def screen_to_image(scr):
    img = canvas(256, 192)
    for y in range(192):
        off = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2)
        for cx in range(32):
            ink, paper = attr_colours(scr[6144 + (y >> 3) * 32 + cx])
            bits = scr[off + cx]
            for b in range(8):
                img[y][cx * 8 + b] = ink if bits & (0x80 >> b) else paper
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extracted")
    ap.add_argument("--out", default="assets")
    a = ap.parse_args()
    src = a.extracted
    ram = open(os.path.join(src, "ram48.bin"), "rb").read()
    bank3 = open(os.path.join(src, "bank3.bin"), "rb").read()
    scr = open(os.path.join(src, "screen.scr"), "rb").read()
    out = a.out
    for d in ("", "rooms", "data"):
        os.makedirs(os.path.join(out, d), exist_ok=True)

    def save(name, img):
        write_png(os.path.join(out, name), len(img[0]), len(img), img)
        print("wrote", os.path.join(out, name))

    save("loading_screen.png", screen_to_image(scr))

    # font: 16 x 8 grid of 8x8 glyphs, 1px gaps
    white, black = (255, 255, 255), (0, 0, 0)
    img = canvas(16 * 9 + 1, 8 * 9 + 1, (40, 40, 40))
    for ch in range(128):
        blit_glyph(img, 1 + (ch % 16) * 9, 1 + (ch // 16) * 9, ram[FONT + ch * 8:FONT + ch * 8 + 8], white, black)
    save("font.png", img)

    # tiles
    cols = 16
    rows = (NUM_TILES + cols - 1) // cols
    img = canvas(cols * 9 + 1, rows * 9 + 1, (40, 40, 40))
    for t in range(NUM_TILES):
        blit_glyph(img, 1 + (t % cols) * 9, 1 + (t // cols) * 9, ram[TILES + t * 8:TILES + t * 8 + 8], white, black)
    save("tiles.png", img)

    # blocks (bank 3 paged while rooms are drawn)
    layouts = bank3[:NUM_ROOMS * 160]
    nblocks = max(layouts) + 1
    defs = []
    img = canvas(8 * 18 + 2, ((nblocks + 7) // 8) * 18 + 2, (40, 40, 40))
    for i in range(nblocks):
        d = bank3[BLOCK_DEFS + i * 8:BLOCK_DEFS + i * 8 + 8]
        defs.append({"index": i, "attr": d[0], "collision": d[1], "flags": d[2], "tiles": list(d[4:8]),
                     "used": i in set(layouts)})
        ink, paper = attr_colours(d[0])
        x0, y0 = 2 + (i % 8) * 18, 2 + (i // 8) * 18
        for k, t in enumerate(d[4:8]):
            blit_glyph(img, x0 + (k & 1) * 8, y0 + (k >> 1) * 8, ram[TILES + t * 8:TILES + t * 8 + 8], ink, paper)
    save("blocks.png", img)
    json.dump(defs, open(os.path.join(out, "data", "blocks.json"), "w"), indent=1)

    # room layouts as text grids
    for r in range(NUM_ROOMS):
        lay = layouts[r * 160:(r + 1) * 160]
        with open(os.path.join(out, "rooms", "room_%02d.txt" % r), "w") as f:
            for y in range(10):
                f.write(" ".join("%02X" % v for v in lay[y * 16:(y + 1) * 16]) + "\n")
    print("wrote %d room layouts" % NUM_ROOMS)

    # Magic Knight: 8 frames of 3 bytes x 32 lines; rendered with the mask as alpha
    img = canvas(8 * 26 + 2, 34, (0, 0, 0, 0))
    for fr in range(8):
        for y in range(32):
            for bx in range(3):
                g = ram[KNIGHT_GFX + fr * 96 + y * 3 + bx]
                m = ram[KNIGHT_MASK + fr * 96 + y * 3 + bx]
                for b in range(8):
                    bit = 0x80 >> b
                    x = 2 + fr * 26 + bx * 8 + b
                    if g & bit:
                        img[1 + y][x] = (255, 255, 255, 255)
                    elif not (m & bit):
                        img[1 + y][x] = (0, 0, 0, 255)
    save("knight.png", img)

    # decoration table (width, height in cells, data pointer); data is drawn by
    # the game's own routine in tools/asset_render.c, the table is kept for reference
    table = []
    for i in range(45, 120):
        o = DECOR_TABLE + i * 4
        w, h, p = ram[o], ram[o + 1], ram[o + 2] | ram[o + 3] << 8
        if not (1 <= w <= 16 and 1 <= h <= 16):
            continue
        table.append({"index": i, "w": w, "h": h, "ptr": "0x%04X" % p})
    json.dump(table, open(os.path.join(out, "data", "decorations.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
