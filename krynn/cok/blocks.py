"""Block ids for the overhead combat map.

Every cell of the combat grid that is not plain floor is a *block*, and
every block kind has a fixed id so its graphics can be redrawn later
(drop a PNG named after the id into remake/art/blocks/). The ids:

    W<area>-<walldef>-<nn>   a wall: walldef entry (hex) of disk area 1/2,
                             wall style nn (01-15, as the 3D map numbers it)
    D<area>-<walldef>-<nn>   a door in that wall style
    EDGE                     outside the 16x16 map
    F-DUNG                   dungeon floor (DUNGCOM tile 22)
    F-WILD-<nn>              outdoor ground (WILDCOM tile nn)
    O-WILD-<nn>              outdoor obstacle (WILDCOM tile nn: trees, rocks...)

`catalogue(files)` lists every wall/door id the game's scripts can load,
with what each one is, so the reference pictures and the list stay in step.
"""
from .dax import Container
from .ecl import EclBlock
from .geo import load_walldef

DUNGEON_FLOOR = 'F-DUNG'
DUNGEON_FLOOR_TILE = 22
EDGE = 'EDGE'

# WILDCOM tiles (24x24): which are ground and which block movement
WILD_GROUND = (12, 13, 14, 15, 22, 23, 24, 25, 26, 27, 28)
WILD_OBSTACLES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 16, 17, 18, 19, 20, 21)
WILD_NAMES = {0: 'dead tree', 1: 'dead tree', 2: 'dead tree', 3: 'dead tree', 4: 'bush',
              5: 'bush', 6: 'tree', 7: 'tree', 8: 'tree', 9: 'tree', 10: 'fallen log',
              11: 'fallen log', 16: 'thorn bush', 17: 'flowering bush', 18: 'rocks',
              19: 'rocks', 20: 'rocks', 21: 'rocks'}


def wall_id(area, walldef, style):
    return 'W%s-%02X-%02d' % (area, walldef, style)


def door_id(area, walldef, style):
    return 'D%s-%02X-%02d' % (area, walldef, style)


def wild_ground(n):
    return 'F-WILD-%02d' % n


def wild_obstacle(n):
    return 'O-WILD-%02d' % n


def for_wall_type(slots, area, t, door):
    """Block id for 3D wall type t (1-15) with the wall sets now loaded."""
    slot, style = (t - 1) // 5, (t - 1) % 5
    src = slots.source[slot] if slots is not None and slot < 3 else None
    if src is None:
        return 'W%s-XX-%02d' % (area, t)
    wid, part = src
    n = part * 5 + style + 1
    return door_id(area, wid, n) if door else wall_id(area, wid, n)


def parse(block):
    """id -> dict(kind, area, walldef, style) (None fields when not used)."""
    k = block[:1]
    if k in 'WD' and block[1:2].isdigit():
        area, wid, n = block[1:].split('-')
        return dict(kind='door' if k == 'D' else 'wall', area=area,
                    walldef=None if wid == 'XX' else int(wid, 16), style=int(n))
    if block.startswith(('F-WILD-', 'O-WILD-')):
        return dict(kind='ground' if block[0] == 'F' else 'obstacle', tile=int(block[-2:]))
    if block == DUNGEON_FLOOR:
        return dict(kind='floor', tile=DUNGEON_FLOOR_TILE)
    return dict(kind='edge')


def catalogue(gf):
    """[(id, description)] for every wall and door the scripts load, plus the rest."""
    out = []
    for area in ('1', '2'):
        wd = Container(gf.read('walldef%s.dax' % area), 'walldef%s.dax' % area)
        used = {}
        ecl = Container(gf.read('ecl%s.dax' % area), 'ecl%s.dax' % area)
        for b in ecl.ids():
            blk = EclBlock(ecl.get(b), b)
            for ins in blk.trace().values():
                if ins.op == 0x37:          # LOAD PIECES slot1, slot2, slot3
                    for a in ins.args:
                        if a.code == 0 and a.value in wd:
                            used.setdefault(a.value, set()).add(b)
        for wid in wd.ids():
            sets = load_walldef(wd.get(wid))
            where = ', '.join('ECL %02X' % b for b in sorted(used.get(wid, ()))) or 'not loaded by any script'
            for k in range(len(sets)):
                for style in range(5):
                    n = k * 5 + style + 1
                    out.append((wall_id(area, wid, n), 'wall, area %s walldef %02X style %d (%s)' % (area, wid, n, where)))
                    out.append((door_id(area, wid, n), 'door in that wall'))
    out.append((EDGE, 'outside the 16x16 map'))
    out.append((DUNGEON_FLOOR, 'dungeon floor (DUNGCOM tile %d)' % DUNGEON_FLOOR_TILE))
    for n in WILD_GROUND:
        out.append((wild_ground(n), 'outdoor ground (WILDCOM tile %d)' % n))
    for n in WILD_OBSTACLES:
        out.append((wild_obstacle(n), 'outdoor %s (WILDCOM tile %d)' % (WILD_NAMES.get(n, 'obstacle'), n)))
    return out
