#!/usr/bin/env python3
"""Checks the remake is physically completable.

Explores every position Magic Knight can stand on, using the real movement
code, starting from the start room and following room exits (with every
barrier opened and the lift able to reach all floors), then reports objects
and characters that cannot be reached.

    python3 remake/tests/reachability.py [--closed]   (--closed: barriers shut)
"""
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
from sbremake.assets import Assets  # noqa: E402
from sbremake.game import Game, LIFT  # noqa: E402
from sbremake.world import Knight, HIT_X0, HIT_X1  # noqa: E402


def settle(kn, geo, inputs, limit=400):
    """Run inputs (left, right, jump) until the knight stands still on ground.
    Returns exit side or None."""
    for i in range(limit):
        out = kn.update(geo, *inputs(i))
        if out:
            return out
        if i > 0 and kn.jump < 0 and kn.on_ground(geo):
            return None
    return None


def main():
    closed = "--closed" in sys.argv
    pygame.init()
    pygame.display.set_mode((320, 240))
    g = Game(Assets(os.path.join(os.path.dirname(HERE), "data")))
    g.new_game()
    if not closed:
        g.flags.update(wall_down=True, tunnel_open=True, bridge=True, lift_fixed=True)
        o = g.objects[29]
        o["holder"], o["room"], o["px"], o["py"] = None, 46, 120, 136
        # the two lumps of brickwork stacked as a step in front of the tower column
        for i, py in ((25, 168), (44, 152)):
            o = g.objects[i]
            o["holder"], o["room"], o["px"], o["py"] = None, 9, 88, py
    start = (g.room, int(g.knight.x), int(g.knight.y))
    seen = set()
    q = deque([start])
    while q:
        room, x, y = q.popleft()
        if (room, x, y) in seen:
            continue
        seen.add((room, x, y))
        moves = []
        for dx in (-1, 1):                     # walk a few pixels
            moves.append(lambda i, d=dx: (d < 0, d > 0, False) if i < 4 else (False, False, False))
        for dx in (-1, 0, 1):                  # jump (holding the direction for the whole jump)
            moves.append(lambda i, d=dx: (d < 0, d > 0, i == 0))
        if g.first_room_floor(room) is not None:
            g.flags["lift_floor"] = g.first_room_floor(room)   # lift waiting here
        for mv in moves:
            g.room = room
            geo = g.geo(room)
            kn = Knight(x, y)
            side = settle(kn, geo, mv)
            if side:
                left, right = g.exits(room)
                dests = [left] if side == "left" else [right]
                if room == LIFT and side == "right":
                    dests = [1 + 8 * k for k in range(7)]
                for d in dests:
                    if d is None:
                        continue
                    if d == LIFT:
                        g.flags["lift_floor"] = (room - 1) // 8
                    g.room = d
                    g.knight = Knight(kn.x, kn.y)
                    g.enter_room(d, side)
                    gk = g.knight
                    gs = settle(gk, g.geo(d), lambda i: (False, False, False))
                    if not gs:
                        q.append((d, int(gk.x), int(gk.y)))
                continue
            q.append((room, int(kn.x), int(kn.y)))
    rooms = {r for r, _, _ in seen}
    print("reachable rooms: %d / %d" % (len(rooms), len(g.g["rooms"])))
    missing = sorted(set(range(len(g.g["rooms"]))) - rooms)
    if missing:
        print("unreached rooms:", missing)
    bad = 0
    for o in g.objects:
        if o["room"] is None or o["holder"] is not None:
            continue
        ok = False
        for (r, x, y) in seen:
            if r != o["room"]:
                continue
            g.knight = Knight(x, y)
            if g.near(o):
                ok = True
                break
        if not ok:
            bad += 1
            print("UNREACHABLE object %2d %-18s room %2d (%s) at %d,%d" % (o["id"], o["name"], o["room"],
                                                                            g.g["rooms"][o["room"]]["name"], o["px"], o["py"]))
    for c in g.chars:
        if c["room"] is not None and c["room"] not in rooms:
            bad += 1
            print("UNREACHABLE character", c["name"], "room", c["room"])
    print("OK" if not bad else "%d problems" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
