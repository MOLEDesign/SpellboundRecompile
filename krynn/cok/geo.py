"""GEO map blocks and WALLDEF wall sets.

GEO entry (0x402 bytes): u16 header, then four 16x16 byte planes, row major
(index = y*16 + x)::

    0x000  hi nibble: wall type facing north, lo nibble: east
    0x100  hi nibble: wall type facing south, lo nibble: west
    0x200  square flags/backdrop byte (bit 7: outdoors/no sky, see engine)
    0x300  door bits, 2 per side: bits 0-1 north, 2-3 east, 4-5 south, 6-7 west

Wall type 0 means open; 1-15 select a wall set slot ((t-1)//5) and a wall
style within it ((t-1)%5). Directions are 0=N 2=E 4=S 6=W.

WALLDEF entry: one or more 780-byte wall sets; each is 5 styles x 156 bytes
of 8x8 symbol ids for every position of the 3D view (see view3d.py).
"""
N, E, S, W = 0, 2, 4, 6
DX = (0, 1, 1, 1, 0, -1, -1, -1)
DY = (-1, -1, 0, 1, 1, 1, 0, -1)


class Square:
    __slots__ = ('walls', 'doors', 'flags')

    def __init__(self, walls, doors, flags):
        self.walls = walls        # {dir: wall type}
        self.doors = doors        # {dir: door bits}
        self.flags = flags


class GeoMap:
    SIZE = 16

    def __init__(self, data, id=None):
        if len(data) < 0x402:
            raise ValueError('GEO block too short')
        self.id = id
        d = data[2:0x402]
        self.raw = bytes(d)
        self.squares = []
        for y in range(16):
            row = []
            for x in range(16):
                i = y * 16 + x
                a, b, f, door = d[i], d[0x100 + i], d[0x200 + i], d[0x300 + i]
                row.append(Square({N: a >> 4, E: a & 15, S: b >> 4, W: b & 15},
                                  {N: door & 3, E: door >> 2 & 3, S: door >> 4 & 3, W: door >> 6 & 3},
                                  f))
            self.squares.append(row)

    def square(self, x, y, wrap=True):
        if not (0 <= x < 16 and 0 <= y < 16):
            if not wrap:
                return None
            x %= 16
            y %= 16
        return self.squares[y][x]

    def wall(self, x, y, d, wrap=True):
        sq = self.square(x, y, wrap)
        return sq.walls[d] if sq else 0

    def door(self, x, y, d):
        """Door bits for the side, 1 when there is no wall (as the engine does)."""
        sq = self.square(x, y)
        return sq.doors[d] if sq.walls[d] else 1

    def ascii(self, party=None):
        lines = []
        for y in range(16):
            top, mid = '', ''
            for x in range(16):
                s = self.squares[y][x]
                top += '+' + ('--' if s.walls[N] else '  ')
                c = '  '
                if party and (x, y) == party[:2]:
                    c = '^>v<'[party[2] // 2] * 2
                mid += ('|' if s.walls[W] else ' ') + c
            lines.append(top + '+')
            lines.append(mid + ('|' if self.squares[y][15].walls[E] else ' '))
        lines.append('+--' * 16 + '+')
        return '\n'.join(lines)


class WallSet:
    SIZE = 780

    def __init__(self, data):
        self.styles = [bytes(data[i * 156:(i + 1) * 156]) for i in range(5)]


def load_walldef(data):
    return [WallSet(data[o:o + WallSet.SIZE]) for o in range(0, len(data) - WallSet.SIZE + 1, WallSet.SIZE)]
