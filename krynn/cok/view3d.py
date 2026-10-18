"""The Gold Box first-person view: 11x11 cells of 8x8 symbols (88x88 px).

Each wall style (156 bytes of a WALLDEF set) is a list of patches; a patch
is a small rectangle of symbol ids for one wall position. PATCHES gives
(start offset, columns, rows) for:

    0 far, facing            1 far, left side         2 far, right side
    3 middle, facing         4 middle, left side      5 middle, right side
    6 near, facing           7 near, left side        8 near, right side
    9 far, edge between two facing walls

The view is drawn back to front: two squares ahead, then one, then the
party's own square. Symbol id 0 is empty; ids below 0x2E come from the
common symbol set (8X8D block 0xCB), higher ids from the wall set slot.
"""
from .geo import DX, DY

PATCHES = [(0, 1, 2), (2, 1, 4), (6, 1, 4), (10, 3, 4), (22, 2, 8),
           (38, 2, 8), (54, 7, 8), (110, 2, 11), (132, 2, 11), (1, 1, 2)]

# screen cell (row, column) of each patch kind, relative to the view origin
ROW = [4, 3, 3, 3, 1, 1, 1, 0, 0, 4]
COL = [5, 4, 6, 4, 2, 7, 2, 0, 9, 5]


def wall_patches(geo, x, y, facing):
    """Yield (patch kind, wall type, row, col) in drawing order."""
    left, behind, right = (facing + 6) % 8, (facing + 4) % 8, (facing + 2) % 8

    def wall(px, py, d):
        return geo.wall(px, py, d)

    sx = x + 2 * DX[facing]
    sy = y + 2 * DY[facing]

    # --- two squares ahead -------------------------------------------------
    for side, other, step in ((left, right, -2), (right, left, 2)):
        tx, ty, col, prev = sx, sy, 0, 0
        for _ in range(4):
            t = wall(tx, ty, facing)
            if not (0 <= tx < 16 and 0 <= ty < 16) and wall(tx, ty, other) == 0:
                prev = 0
            edge = 1 if step < 0 else -1
            if t:
                if prev:
                    yield 9, prev, ROW[9], COL[9] + col + edge
                prev = t
                yield 0, t, ROW[0], COL[0] + col
            else:
                if prev and wall(tx - DX[side], ty - DY[side], side):
                    yield 9, prev, ROW[9], COL[9] + col + edge
                prev = 0
            col += step
            tx += DX[side]
            ty += DY[side]
    for kind, side, step in ((1, left, -2), (2, right, 2)):
        tx, ty, col = sx, sy, 0
        for i in range(3):
            t = wall(tx, ty, side)
            if t:
                adj = 0 if i == 0 else (-1 if kind == 1 else 1)
                yield kind, t, ROW[kind], COL[kind] + col + adj
            col += step
            tx += DX[side]
            ty += DY[side]

    # --- one square ahead -------------------------------------------------
    mx, my = sx + DX[behind], sy + DY[behind]
    for side, back, kind, start, step in ((left, right, 4, -6, 3), (right, left, 5, 6, -3)):
        tx, ty, col = mx + 2 * DX[side], my + 2 * DY[side], start
        for _ in range(3):
            t = wall(tx, ty, facing)
            if t:
                yield 3, t, ROW[3], COL[3] + col
            t = wall(tx, ty, side)
            if t:
                yield kind, t, ROW[kind], COL[kind] + col
            col += step
            tx += DX[back]
            ty += DY[back]

    # --- the party's square -------------------------------------------------
    nx, ny = mx + DX[behind], my + DY[behind]
    for side, back, kind, start, step in ((left, right, 7, -7, 7), (right, left, 8, 7, -7)):
        tx, ty, col = nx + DX[side], ny + DY[side], start
        for _ in range(2):
            t = wall(tx, ty, facing)
            if t:
                yield 6, t, ROW[6], COL[6] + col
            t = wall(tx, ty, side)
            if t:
                yield kind, t, ROW[kind], COL[kind] + col
            col += step
            tx += DX[back]
            ty += DY[back]


def symbol_cells(geo, x, y, facing, wallsets):
    """Yield (row, col, wall slot, symbol id) for every non-empty cell.

    wallsets: list of 3 WallSet objects (or None) for wall type slots.
    """
    for kind, t, row0, col0 in wall_patches(geo, x, y, facing):
        slot, style = (t - 1) // 5, (t - 1) % 5
        ws = wallsets[slot] if slot < len(wallsets) else None
        if ws is None:
            continue
        data = ws.styles[style]
        start, cols, rows = PATCHES[kind]
        i = start
        for r in range(row0, row0 + rows):
            for c in range(col0, col0 + cols):
                sym = data[i] if i < len(data) else 0
                i += 1
                if sym and 0 <= r <= 10 and 0 <= c <= 10:
                    yield r, c, slot, sym


SET_BASE = (0x01, 0x2E, 0x74, 0xBA, 0x100)   # first global symbol id of set 0..4
TRANSPARENT = 13


def resolve(sym):
    """Global symbol id -> (symbol set, index)."""
    for s in (4, 3, 2, 1, 0):
        if sym >= SET_BASE[s]:
            return s, sym - SET_BASE[s]
    return 0, 0


class WallSlots:
    """The three wall slots plus the symbol sets, loaded like the engine does.

    load(slot, walldef_id) places every 780-byte set of that WALLDEF entry in
    consecutive slots starting at `slot`. Symbol ids >= 0x2D in the set are
    shifted by the distance of the *starting* slot from slot 1, so a set may
    also use symbols belonging to the following slots.
    """

    def __init__(self, walldef, symbols, common):
        self.walldef = walldef        # Container of WALLDEF
        self.symbols = symbols        # Container of 8X8D
        self.sets = [common, None, None, None]
        self.walls = [None, None, None]
        self.shift = [0, 0, 0]
        self.ids = [None, None, None]
        self.source = [None, None, None]   # (walldef id, part) shown in each slot

    def load(self, slot, block_id):
        from .geo import load_walldef
        from .gfx import decode_block
        sets = load_walldef(self.walldef.get(block_id))
        shift = SET_BASE[slot] - SET_BASE[1]
        for k, ws in enumerate(sets):
            s = slot + k
            if 1 <= s <= 3:
                self.walls[s - 1] = ws
                self.shift[s - 1] = shift
                self.source[s - 1] = (block_id, k)
                tid = block_id * 10 + k + 1 if len(sets) > 1 else block_id
                pic = decode_block(self.symbols.get(tid)) if tid in self.symbols else None
                self.sets[s] = pic.frames if pic else None
        self.ids[slot - 1] = block_id


class Renderer:
    """Builds an 88x88 index buffer of the view from a GeoMap and WallSlots."""
    W = H = 88

    def background(self, sky=0, ground=8):
        buf = bytearray(self.W * self.H)
        for y in range(self.H):
            c = sky if y < 44 else (0 if y < 46 else ground)
            buf[y * 88:(y + 1) * 88] = bytes((c,)) * 88
        return buf

    def render(self, geo, x, y, facing, slots, sky=0, ground=8):
        buf = self.background(sky, ground)
        for r, c, slot, sym in symbol_cells(geo, x, y, facing, slots.walls):
            if sym >= 0x2D:
                sym += slots.shift[slot]
            s, i = resolve(sym)
            tiles = slots.sets[s] if s < len(slots.sets) else None
            if not tiles or i >= len(tiles):
                continue
            tile = tiles[i]
            for ty in range(8):
                o = (r * 8 + ty) * 88 + c * 8
                for tx in range(8):
                    v = tile[ty * 8 + tx]
                    if v != TRANSPARENT:
                        buf[o + tx] = v
        return buf
