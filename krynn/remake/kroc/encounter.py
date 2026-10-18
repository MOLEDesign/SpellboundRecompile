"""Builds a Battle from the game state: party records, monster records, map."""
import random

from cok import blocks

from cok import items as I

from . import magic, magic_items

from .combat import (Attack, Battle, Combatant, ENEMY, PARTY, SPAN_X, SPAN_Y, SQUARE,
                     Missile, dungeon_arena, open_arena, DYING, DEAD)

HOOPAK = 67       # the kender sling-staff: fires stones, never used up


def make_missile(owner_items, types, thac0):
    found = I.best_missile(owner_items, types)
    if found is None:
        return None
    item, t, ammo = found
    n, size, bonus = t.dice
    consumed = None
    if ammo is not None:
        consumed = 'ammo'
    elif t.flags & I.THROWN and t.index != HOOPAK:
        ammo, consumed = item, 'thrown'      # darts, javelins: the weapon itself flies
    name = I.WEAPONS.get(t.index, item.name)
    ammo_name = 'quarrels' if t.ammo == I.QUARREL else ('arrows' if t.ammo == I.ARROW else
                                                        (name.lower() + 's' if consumed else ''))
    return Missile(name, n or 1, size or 4, bonus, max(1, t.half_attacks // 2), t.range, thac0,
                   ammo, ammo_name, consumed)


def _s8(b):
    return b - 256 if b > 127 else b


# the mindless and the bound never run (undead, golems, conjured things)
FEARLESS = ('SKELET', 'SPECTR', 'ZOMBIE', 'GHOUL', 'GHAST', 'WIGHT', 'WRAITH', 'SPECTRE', 'GHOST',
            'MUMMY', 'VAMPIRE', 'LICH', 'DEATH KNIGHT', 'SKULL', 'GOLEM', 'ELEMENTAL', 'UNDEAD',
            'SHADOW', 'JUJU')


def morale(name, hd):
    """d100 score a monster must not exceed to keep fighting (None: never breaks)."""
    if any(w in name.upper() for w in FEARLESS):
        return None
    return min(95, 40 + 6 * hd)


def monster_combatant(world, mid, n, icon=None):
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
    # LOAD MONSTER's third operand picks the combat icon (CPICn.DAA id)
    ready, _ = world.files.combat_icon(icon, area) if icon is not None else (None, None)
    if ready is None:
        icon = mid
        ready, _ = world.files.combat_icon(mid, area)
    if ready is not None:
        size = (max(1, ready.width // 24), max(1, ready.height // 24))
    c = Combatant(name, ENEMY, hp, hp, 60 - rec[0x113], 60 - rec[0x59], attacks, move,
                  ('monster', icon, area), size=size, xp=rec[0x130] | rec[0x131] << 8)
    c.spells = [x for x in rec[0x1E:0x59] if 1 <= x <= 94]
    c.hd = rec[0xD6] or 1
    c.levels = {'C': c.hd, 'M': c.hd}
    c.save_spell = rec[0xD4] or 16
    c.morale = morale(name, c.hd)
    its = world.files.monster_items(mid, area)
    c.missile = make_missile(its, world.files.item_types(), c.thac0)
    if c.missile is not None and c.missile.ammo is not None:
        c.missile.ammo = I.Item(c.missile.ammo_name, 0, True, 20)    # monsters' own supply
    return c


def party_combatant(ch, types=None, day=0, words=None):
    n, size, bonus = ch.weapon
    lv = ch.levels
    # fighters and knights from 7th level, rangers from 8th, strike 3 times in 2 rounds
    half = 3 if max(lv.get('fighter', 0), lv.get('knight', 0), lv.get('paladin', 0)) >= 7 \
        or lv.get('ranger', 0) >= 8 else 2
    c = Combatant(ch.name, PARTY, ch.hp, ch.hp_max, ch.ac, ch.thac0, [Attack(half, n, size, bonus)],
                  ch.move, ('party', ch), ref=ch)
    if types:
        c.missile = make_missile(ch.items, types,
                                 ch.base_thac0 - I.dex_missile_bonus(ch.stats.get('DEX', 10)))
    c.spells = ch.spells               # the same list: spells cast stay used until a rest
    if types and words:
        c.item_powers = lambda: magic_items.powers(ch, words, types)
        c.slayer = magic_items.slayer(ch, words, types)
    c.levels = magic.caster_levels(ch)
    c.hd = ch.top_level
    # the moons of Krynn: a mage's saving throws and casting level wax and wane
    save, _, level = magic.moon_effect(ch, day)
    if c.levels['M']:
        c.levels['M'] = max(1, c.levels['M'] + level)
    c.save_spell = ch.save_spell - save
    if ch.dead:
        c.status = DEAD
    elif ch.hp <= 0:
        c.status = DYING
    c.auto = False
    return c


def build(world, monsters, rng=None):
    rng = rng or random.Random()
    types = world.files.item_types()
    words = world.files.item_words()
    party = [party_combatant(ch, types, getattr(world, 'day', 0), words) for ch in world.party if not ch.dead]
    enemies = []
    for mid, count, pic in monsters:
        for k in range(max(1, count)):
            enemies.append(monster_combatant(world, mid, k, pic))
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
