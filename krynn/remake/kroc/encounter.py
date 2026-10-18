"""Builds a Battle from the game state: party records, monster records, map."""
import random

from cok import blocks

from .combat import (Attack, Battle, Combatant, ENEMY, PARTY, SPAN_X, SPAN_Y, SQUARE,
                     dungeon_arena, open_arena, DYING, DEAD)


def _s8(b):
    return b - 256 if b > 127 else b


def monster_combatant(world, mid, n):
    """A monster from its MONnCHA record (offsets in docs/FORMATS.md)."""
    area = getattr(world.files, 'area', None)
    rec = world.files.monster(mid, area)
    if rec is None:
        return Combatant('MONSTER %d' % mid, ENEMY, 8, 8, 7, 19, [Attack(2, 1, 6)], 9,
                         ('monster', mid, area), xp=10)
    name = rec[1:1 + rec[0]].decode('latin-1')
    hp = rec[0x62] or 4
    attacks = []
    for half, dice, size, bonus in ((rec[0x10B], rec[0x10D], rec[0x10F], _s8(rec[0x111])),
                                    (rec[0x10C], rec[0x10E], rec[0x110], _s8(rec[0x112]))):
        if half:
            attacks.append(Attack(half, dice, size, bonus))
    if not attacks:
        attacks = [Attack(2, 1, 4)]
    move = min(rec[0xD5] or 6, 12)          # flying speeds are not used on the ground
    size = (1, 1)
    ready, _ = world.files.combat_icon(mid, area)
    if ready is not None:
        size = (max(1, ready.width // 24), max(1, ready.height // 24))
    return Combatant(name, ENEMY, hp, hp, 60 - rec[0x113], 60 - rec[0x59], attacks, move,
                     ('monster', mid, area), size=size, xp=rec[0x130] | rec[0x131] << 8)


def party_combatant(ch):
    n, size, bonus = ch.weapon
    c = Combatant(ch.name, PARTY, ch.hp, ch.hp_max, ch.ac, ch.thac0, [Attack(2, n, size, bonus)],
                  ch.move, ('party', ch), ref=ch)
    if ch.dead:
        c.status = DEAD
    elif ch.hp <= 0:
        c.status = DYING
    c.auto = False
    return c


def build(world, monsters, rng=None):
    rng = rng or random.Random()
    party = [party_combatant(ch) for ch in world.party if not ch.dead]
    enemies = []
    for mid, count, _pic in monsters:
        for k in range(max(1, count)):
            enemies.append(monster_combatant(world, mid, k))
    if world.in_dungeon and world.geo is not None:
        area = getattr(world, 'map_area', '1') or '1'
        arena, _ = dungeon_arena(
            world.geo, world.x, world.y,
            lambda t: blocks.for_wall_type(world.slots, area, t, False),
            lambda t: blocks.for_wall_type(world.slots, area, t, True),
            blocks.DUNGEON_FLOOR)
        start = (SPAN_X * SQUARE + 2, SPAN_Y * SQUARE + 2)
        facing = world.facing
    else:
        ground = [27, 28] * 6 + [12, 13, 14, 15, 22, 23, 24]   # mostly bare ground
        arena = open_arena(rng, floor_ids=[blocks.wild_ground(n) for n in ground],
                           scatter=[blocks.wild_obstacle(n) for n in blocks.WILD_OBSTACLES])
        start = (arena.w // 2, arena.h // 2 + 4)
        facing = 0
    b = Battle(arena, party, enemies, rng)
    b.place(start, facing)
    return b
