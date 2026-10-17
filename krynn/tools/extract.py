#!/usr/bin/env python3
"""Extract everything from your copy of Champions of Krynn (Amiga).

    python3 tools/extract.py [SOURCE] [--out extracted] [--no-asm]

SOURCE is the .zip of ADF images, a folder of .adf files or a folder of
installed files (default: looked up in krynn/original/). Writes:

    files/            every file from the disks, as stored
    pictures/         every picture, animation and sprite as PNG
    symbols/          8x8 wall/symbol sets as PNG sheets
    walls/            each wall style drawn at the near position
    maps/             GEO maps as ASCII and PNG
    ecl/              ECL event scripts, disassembled
    lbm/              the IFF title screens and character icons
    krynn.asm         annotated 68000 disassembly of "game" (needs capstone)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from cok import gfx, view3d  # noqa: E402
from cok.dax import Container  # noqa: E402
from cok.ecl import EclBlock  # noqa: E402
from cok.gamefiles import GameFiles  # noqa: E402
from cok.geo import GeoMap, load_walldef  # noqa: E402
from cok.ilbm import ILBM  # noqa: E402
from cok.png import write_png  # noqa: E402


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb' if isinstance(data, bytes) else 'w') as f:
        f.write(data)


def sheet(path, images, pal, cols=16, scale=3, transparent=None):
    """images: list of (w, h, index bytes)."""
    w = max(i[0] for i in images)
    h = max(i[1] for i in images)
    rows = (len(images) + cols - 1) // cols
    W, H = cols * (w + 1), rows * (h + 1)
    px = [(48, 0, 48, 255)] * (W * H)
    for n, (iw, ih, data) in enumerate(images):
        ox, oy = (n % cols) * (w + 1), (n // cols) * (h + 1)
        for y in range(ih):
            for x in range(iw):
                c = data[y * iw + x]
                px[(oy + y) * W + ox + x] = (0, 0, 0, 0) if c == transparent else pal[c] + (255,)
    big = [px[(y // scale) * W + x // scale] for y in range(H * scale) for x in range(W * scale)]
    write_png(path, W * scale, H * scale, big, alpha=True)


def containers(gf, suffixes):
    for name in gf.names():
        if '/' not in name and name.endswith(suffixes):
            yield name, Container(gf.read(name), name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', nargs='?')
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'extracted'))
    ap.add_argument('--no-asm', action='store_true')
    a = ap.parse_args()
    gf = GameFiles(a.source)
    out = a.out
    print('reading', gf.source, gf.disks)

    for name in gf.names():
        write(os.path.join(out, 'files', name), gf.read(name))

    # pictures --------------------------------------------------------------
    n = 0
    for name, c in containers(gf, ('.daa',)):
        if name.startswith(('8x8d', 'pointers')):
            continue
        for i in c.ids():
            pic = gfx.decode_anim(c.get(i)) if c.kind == 'anim' else gfx.decode_block(c.get(i))
            if not pic:
                continue
            key = None
            if name.startswith('sprit'):
                key = gfx.transparent_index(pic)
            gfx.save_png(os.path.join(out, 'pictures', '%s_%02X.png' % (name[:-4], i)), pic, key, scale=2)
            n += 1
    print('pictures:', n)

    # 8x8 symbol sets and wall styles -----------------------------------------
    pal = gfx.EGA * 2
    for name, c in containers(gf, ('.daa',)):
        if not name.startswith('8x8d'):
            continue
        for i in c.ids():
            pic = gfx.decode_block(c.get(i))
            if pic:
                sheet(os.path.join(out, 'symbols', '%s_%02X.png' % (name[:-4], i)),
                      [(8, 8, f) for f in pic.frames], pal, transparent=13)
    for wname, wd in containers(gf, ('.dax',)):
        if not wname.startswith('walldef'):
            continue
        area = wname[7:-4]
        sym = Container(gf.read('8x8d%s.daa' % area), '8x8d%s.daa' % area)
        common = gfx.decode_block(Container(gf.read('8x8d0.daa'), '8x8d0.daa').get(0xCB)).frames
        for wid in wd.ids():
            slots = view3d.WallSlots(wd, sym, common)
            slots.load(1, wid)
            imgs = []
            for k, ws in enumerate(load_walldef(wd.get(wid))):
                for style in range(5):
                    geo = _corridor(k * 5 + style + 1)
                    imgs.append((88, 88, view3d.Renderer().render(geo, 1, 3, 0, slots)))
            sheet(os.path.join(out, 'walls', 'walldef%s_%02X.png' % (area, wid)), imgs, pal, cols=5, scale=2)

    # maps -------------------------------------------------------------------
    for gname, gc in containers(gf, ('.dax',)):
        if not gname.startswith('geo'):
            continue
        for i in gc.ids():
            g = GeoMap(gc.get(i), i)
            write(os.path.join(out, 'maps', '%s_%02X.txt' % (gname[:-4], i)), g.ascii() + '\n')
            _map_png(os.path.join(out, 'maps', '%s_%02X.png' % (gname[:-4], i)), g)
    print('maps done')

    # ECL --------------------------------------------------------------------
    for ename, ec in containers(gf, ('.dax',)):
        if not ename.startswith('ecl'):
            continue
        for i in ec.ids():
            write(os.path.join(out, 'ecl', '%s_%02X.txt' % (ename[:-4], i)), EclBlock(ec.get(i), i).listing() + '\n')
    print('ecl done')

    # IFF pictures -------------------------------------------------------------
    for name in gf.names():
        if name.endswith('.lbm'):
            im = ILBM(gf.read(name))
            p = im.palette + [(0, 0, 0)] * (256 - len(im.palette))
            write_png(os.path.join(out, 'lbm', name[:-4] + '.png'), im.width, im.height,
                      [p[c] for c in im.pixels])

    if not a.no_asm:
        import importlib.util
        if importlib.util.find_spec('capstone') is None:
            print('skipping disassembly (pip install capstone)')
        else:
            import subprocess
            game = os.path.join(out, 'files', 'game')
            subprocess.check_call([sys.executable, os.path.join(HERE, 'disasm68k.py'), game,
                                   '-o', os.path.join(out, 'krynn.asm')])
    print('done ->', os.path.abspath(out))


def _corridor(wall):
    """A tiny map: a corridor with a wall of the given type ahead and at the sides."""
    raw = bytearray(0x402)
    d = raw[2:]

    def setw(x, y, side, t):
        i = y * 16 + x
        if side in (0, 2):
            sh = 4 if side == 0 else 0
            d[i] = (d[i] & ~(15 << sh)) | (t << sh)
        else:
            sh = 4 if side == 4 else 0
            d[0x100 + i] = (d[0x100 + i] & ~(15 << sh)) | (t << sh)
    for y in range(1, 4):
        setw(1, y, 6, wall)
        setw(1, y, 2, wall)
    setw(1, 1, 0, wall)
    raw[2:] = d
    return GeoMap(bytes(raw))


def _map_png(path, g, cell=12):
    W = 16 * cell + 1
    px = [(24, 24, 32)] * (W * W)
    col = [(0, 0, 0), (200, 200, 200), (230, 180, 80), (120, 220, 120)]

    def line(x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px[y * W + x] = c
    for y in range(16):
        for x in range(16):
            s = g.squares[y][x]
            x0, y0 = x * cell, y * cell
            if s.flags & 0x7F:
                line(x0 + cell // 2 - 1, y0 + cell // 2 - 1, x0 + cell // 2, y0 + cell // 2, (90, 90, 140))
            for d, (a, b, c2, e) in ((0, (x0, y0, x0 + cell, y0)), (4, (x0, y0 + cell, x0 + cell, y0 + cell)),
                                     (6, (x0, y0, x0, y0 + cell)), (2, (x0 + cell, y0, x0 + cell, y0 + cell))):
                if s.walls[d]:
                    door = s.doors[d]
                    line(a, b, c2, e, col[1] if door in (0, 1) else col[2 + (door & 1)])
    write_png(path, W, W, px)


if __name__ == '__main__':
    main()
