#!/usr/bin/env python3
"""Checks against your copy of the game (skipped when it is not found).

    python3 tests/run_tests.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'remake'))

from cok import gfx  # noqa: E402
from cok.dax import Container  # noqa: E402
from cok.ecl import EclBlock, OPCODES  # noqa: E402
from cok.gamefiles import GameFiles  # noqa: E402
from cok.geo import GeoMap  # noqa: E402


def test_containers(gf):
    for name in gf.names():
        if '/' in name or not name.endswith(('.dax', '.daa')) or name == 'pointers.daa':
            continue
        c = Container(gf.read(name), name)
        for i in c.ids():
            e = c.entries[i]
            data = c.get(i)
            if e.raw_size is not None and not (name.startswith('8x8d') and i == 0xC9):
                assert len(data) == e.raw_size, (name, i)


def test_pictures(gf):
    n = 0
    for name in gf.names():
        if '/' in name or not name.endswith('.daa') or name.startswith(('8x8d', 'pointers')):
            continue
        c = Container(gf.read(name), name)
        for i in c.ids():
            p = gfx.decode_anim(c.get(i)) if c.kind == 'anim' else gfx.decode_block(c.get(i))
            assert p and p.frames and len(p.frames[0]) == p.width * p.height, (name, i)
            n += 1
    assert n > 250, n


def test_ecl(gf):
    for name in ('ecl1.dax', 'ecl2.dax'):
        c = Container(gf.read(name), name)
        for i in c.ids():
            e = EclBlock(c.get(i), i)
            code = e.trace()
            assert all(ins.op in OPCODES for ins in code.values()), (name, i)
            if i != 0x39:     # the demo block: its tail is only reached by the demo player
                assert sum(ins.size for ins in code.values()) > len(e.code) * 0.8, (name, i)


def test_geo(gf):
    for name in ('geo1.dax', 'geo2.dax'):
        c = Container(gf.read(name), name)
        for i in c.ids():
            g = GeoMap(c.get(i), i)
            assert max(t for row in g.squares for s in row for t in s.walls.values()) <= 15


def test_story_reaches_throtl(gf):
    """New game -> leave the outpost -> walk to Throtl -> first steps inside."""
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.vm.rng.seed(1)

    def drive(g):
        ans = None
        for _ in range(10000):
            try:
                r = g.send(ans)
            except StopIteration:
                return
            ans = None
            if r[0] == 'menu':
                items = r[1]
                if 'LEAVE' in items:
                    ans = items.index('LEAVE')
                elif 'YES' in items:
                    ans = 1 if w.vm.get_string(0x7B2C) in ('AN OUTPOST', 'WILD') else 0
                else:
                    ans = 0
            elif r[0] == 'combat':
                ans = True
        raise AssertionError('script did not finish')
    drive(w.start())
    for act in ('right', 'forward', 'forward', 'forward', 'forward'):
        drive(w.step(act))
    assert w.vm.block_id == 0x20 and w.in_dungeon and w.geo_id == 0x20, (w.vm.block_id, w.geo_id)
    assert (w.x, w.y) == (7, 13), (w.x, w.y)


def main():
    try:
        gf = GameFiles(sys.argv[1] if len(sys.argv) > 1 else None)
    except FileNotFoundError as e:
        print('SKIP:', e)
        return 0
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            try:
                fn(gf)
                print('ok  ', name)
            except Exception as e:     # report and continue
                failed += 1
                print('FAIL', name, repr(e))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
