"""Combat graphics: blocks (replaceable by id), floor tiles and icons.

Any block can be redrawn: save remake/art/blocks/<ID>.png and it is used
instead of the built-in look (scaled to the cell size). Without one:
floors and outdoor obstacles use the original 24x24 tiles, and walls and
doors are drawn as solid blocks in the wall's own colour with the id on
them, so every block on screen can be named.
"""
import os
import zlib

import pygame

from cok import blocks, gfx, view3d
from cok.geo import corridor
from cok.ilbm import ILBM

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'art', 'blocks')
ICON_BG = 16                       # background colour of the icon sheets
ICON_RECOLOUR = (1, 2, 3, 4, 6, 7)  # template colours replaced by the character's own
SHEET_COLS = 13
HEAD_BASE = 67                     # first head on the icon sheets


def _indexed(pixels, w, h, palette, key=None):
    s = pygame.Surface((w, h), depth=8)
    s.set_palette(palette)
    pitch = s.get_pitch()
    buf = s.get_buffer()
    if pitch == w:
        buf.write(bytes(pixels))
    else:
        for y in range(h):
            buf.write(bytes(pixels[y * w:(y + 1) * w]), y * pitch)
    del buf
    if key is not None:
        s.set_colorkey(key)
    return s.convert_alpha() if pygame.display.get_surface() else s


class Art:
    def __init__(self, world, font):
        self.world = world
        self.font = font
        self.cache = {}
        self.wall_colours = {}

    # --- blocks -------------------------------------------------------------
    def block(self, bid, size, door_state=None):
        key = ('block', bid, size, door_state)
        if key in self.cache:
            return self.cache[key]
        path = os.path.join(ART, bid + '.png')
        if os.path.exists(path):
            s = pygame.transform.smoothscale(pygame.image.load(path).convert_alpha(), (size, size))
        else:
            s = self._builtin_block(bid, size)
        if door_state in (2, 3):
            s = s.copy()
            pygame.draw.rect(s, (40, 20, 0), (size // 2 - size // 8, size // 2 - size // 8, size // 4, size // 4))
        self.cache[key] = s
        return s

    def _builtin_block(self, bid, size):
        info = blocks.parse(bid)
        if info['kind'] in ('ground', 'obstacle', 'floor'):
            tiles = self._tiles('dungcom' if info['kind'] == 'floor' else 'wildcom')
            if tiles is not None:
                return pygame.transform.scale(tiles[info['tile']], (size, size))
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        if info['kind'] == 'edge':
            s.fill((8, 8, 16))
            return s
        base = self._wall_colour(info)
        if info['kind'] == 'door':
            s.fill((150, 90, 30))
            pygame.draw.rect(s, (90, 50, 10), s.get_rect(), max(1, size // 12))
            pygame.draw.line(s, (90, 50, 10), (size // 2, 2), (size // 2, size - 3), max(1, size // 16))
        else:
            s.fill(base)
            hi = tuple(min(255, c + 40) for c in base)
            lo = tuple(max(0, c - 50) for c in base)
            b = max(1, size // 12)
            pygame.draw.rect(s, hi, (0, 0, size, b))
            pygame.draw.rect(s, hi, (0, 0, b, size))
            pygame.draw.rect(s, lo, (0, size - b, size, b))
            pygame.draw.rect(s, lo, (size - b, 0, b, size))
        if size >= 40:
            t = self.font.render(bid, True, (255, 255, 255))
            t = pygame.transform.smoothscale(t, (size - 4, max(6, t.get_height() * (size - 4) // t.get_width())))
            s.blit(t, (2, size - t.get_height() - 2))
        return s

    def _wall_colour(self, info):
        """Average colour of the original wall style (so blocks look like their wall)."""
        key = (info['area'], info['walldef'], info['style'])
        if key in self.wall_colours:
            return self.wall_colours[key]
        colour = None
        try:
            if info['walldef'] is not None:
                f = self.world.files
                wd = f.container('walldef%s.dax' % info['area'])
                sym = f.container('8x8d%s.daa' % info['area'])
                common = gfx.decode_block(f.container('8x8d0.daa').get(0xCB)).frames
                slots = view3d.WallSlots(wd, sym, common)
                slots.load(1, info['walldef'])
                buf = view3d.Renderer().render(corridor(info['style']), 1, 3, 0, slots, sky=13, ground=13)
                px = [gfx.EGA[c] for c in buf if c != 13 and c < 16]
                if px:
                    colour = tuple(sum(p[i] for p in px) // len(px) for i in range(3))
        except Exception:      # a reference that cannot be drawn just gets a default colour
            colour = None
        if colour is None:
            h = zlib.crc32(repr(key).encode())
            colour = (90 + h % 80, 80 + (h >> 8) % 60, 70 + (h >> 16) % 60)
        self.wall_colours[key] = colour
        return colour

    def _tiles(self, name):
        key = ('tiles', name)
        if key not in self.cache:
            pic = self.world.files.tiles(name)
            self.cache[key] = None if pic is None else [
                _indexed(f, 24, 24, pic.rgb_palette()) for f in pic.frames]
        return self.cache[key]

    # --- icons ----------------------------------------------------------------
    def monster_icon(self, mid, attack=False, area=None):
        key = ('mon', mid, attack, area)
        if key not in self.cache:
            ready, atk = self.world.files.combat_icon(mid, area)
            pic = atk if attack else ready
            if pic is None:
                self.cache[key] = None
            else:
                # icon backgrounds are colour 0
                self.cache[key] = _indexed(pic.frames[0], pic.width, pic.height, pic.rgb_palette(), key=0)
        return self.cache[key]

    def party_icon(self, ch):
        key = ('party', id(ch))
        if key not in self.cache:
            self.cache[key] = self._compose(ch.icon)
        return self.cache[key]

    def _compose(self, icon):
        name = 'chart.lbm' if icon['size'] != 1 else 'chars.lbm'
        sk = ('sheet', name)
        if sk not in self.cache:
            gf = self.world.files.gf
            self.cache[sk] = ILBM(gf.read(name)) if name in gf else None
        im = self.cache[sk]
        if im is None:
            return None

        def cell(n):
            cx, cy = (n % SHEET_COLS) * 24, (n // SHEET_COLS) * 24
            return [im.pixels[(cy + y) * im.width + cx + x] for y in range(24) for x in range(24)]
        body, head = cell(icon['body']), cell(HEAD_BASE + icon['head'])
        merged = [h if h != ICON_BG else b for b, h in zip(body, head)]
        remap = list(range(32))
        for i, c in enumerate(ICON_RECOLOUR):
            col = icon['colours'][i] if i < len(icon['colours']) else 0
            remap[c], remap[c + 8] = col & 15, col >> 4
        pal = list(im.palette) + [(0, 0, 0)] * (32 - len(im.palette))
        # recoloured parts take EGA colours; the rest keeps the sheet's palette
        out_pal = list(pal)
        pixels = []
        for v in merged:
            if v in ICON_RECOLOUR or (v - 8) in ICON_RECOLOUR:
                pixels.append(32 + remap[v])
            else:
                pixels.append(v)
        out_pal = (out_pal + [(0, 0, 0)] * 32)[:32] + gfx.EGA + [(0, 0, 0)] * (256 - 48)
        pixels = [ICON_BG if v == 0 else v for v in pixels]
        return _indexed(pixels, 24, 24, out_pal, key=ICON_BG)
