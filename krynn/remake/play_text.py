#!/usr/bin/env python3
"""Headless text player for the remake's engine: runs the original scripts in
the terminal. Useful to test the VM without graphics.

    python3 play_text.py [--auto N]   (--auto: answer every menu with option 0
                                       and walk randomly for N steps)
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

from kroc.world import World  # noqa: E402


def drive(gen, auto, out):
    answer = None
    while True:
        try:
            req = gen.send(answer)
        except StopIteration:
            return
        answer = None
        kind = req[0]
        if kind == 'print':
            out(('\n' if req[2] else '') + req[1])
        elif kind == 'menu':
            out('  [' + ' | '.join('%d:%s' % (n, t) for n, t in enumerate(req[1])) + ']')
            if auto:
                answer = 0
            else:
                try:
                    answer = int(input('> ') or 0)
                except ValueError:
                    answer = 0
        elif kind == 'combat':
            out('  <combat with %s - auto win>' % req[1])
            answer = True
        elif kind in ('picture', 'block', 'note', 'sprite', 'treasure'):
            out('  <%s %s>' % (kind, ' '.join(str(x) for x in req[1:])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--auto', type=int, default=0)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    random.seed(a.seed)
    w = World(log=print)
    w.vm.rng.seed(a.seed)
    drive(w.start(), a.auto, print)
    steps = a.auto if a.auto else 10 ** 9
    for _ in range(steps):
        where = ('3D map %02X x=%d y=%d facing %s' % (w.geo_id or 0, w.x, w.y, 'NESW'[w.facing // 2])
                 if w.in_dungeon else 'overland %d,%d' % (w.vm.get(0x4BC3), w.vm.get(0x4BC4)))
        if a.auto:
            act = random.choice(['forward', 'forward', 'forward', 'left', 'right', 'search'])
            print('--', where, 'block %02X' % w.vm.block_id, act)
        else:
            act = {'w': 'forward', 'a': 'left', 'd': 'right', 's': 'back', 'f': 'search', 'q': 'quit'}.get(
                input('%s  [w/a/s/d move, f search, q quit] ' % where).strip()[:1], 'forward')
            if act == 'quit':
                return
        drive(w.step(act), a.auto, print)


if __name__ == '__main__':
    main()
