"""Companions who join the party (ADD NPC): built from their monster record.

The monster record is the character layout shifted one byte down from 0x59:
0x59 60-THAC0, 0x5A race, 0x5B class, 0x5C knightly order, 0x5D deity,
0x5E mage order; 0xF9-0x100 class levels; 0x62 hit points, 0x113 60-AC,
0x10D/0x10F/0x111 the first attack's dice, size and bonus, 0xD5 movement.
They fight under the computer's command, and have morale.
"""
from cok.items import Item, WEAPONS

from . import training as T
from .world import Character


def npc_character(world, mid, morale):
    rec = world.files.monster(mid, getattr(world.files, 'area', None))
    if rec is None:
        return None
    name = rec[1:1 + rec[0]].decode('latin-1').strip()
    r = bytearray(0x1AA)
    nm = name.encode('latin-1')[:15]
    r[0:len(nm)] = nm
    r[0x10:0x1C] = rec[0x10:0x1C]                    # abilities
    r[0x1E:0x5A] = rec[0x1E:0x5A]                    # spells
    r[0x5A] = rec[0x59]
    r[0x5B:0x60] = rec[0x5A:0x5F]                    # race, class, order, deity, robe
    r[0x64] = rec[0x62]
    r[0xFE:0x106] = rec[0xF9:0x101]                  # class levels
    r[0x19B] = rec[0x59]
    r[0x19C] = rec[0x113]
    r[0x1A0], r[0x1A2], r[0x1A5] = rec[0x10D] or 1, rec[0x10F] or 6, rec[0x111]
    r[0x1A8] = rec[0x62]
    r[0x1A9] = min(12, rec[0xD5] or 12)
    items = [Item(WEAPONS.get(i.type, i.name), i.type, True, i.quantity if i.type in (5, 7, 30) else 1)
             for i in world.files.monster_items(mid, getattr(world.files, 'area', None))]
    ch = Character(name, bytes(r), items)
    if not any(ch.levels.values()):
        ch.levels['fighter'] = max(1, rec[0xD6])     # a plain soldier: a fighter of its hit dice
    ch.experience = max(T.XP[T.table(ch, c)][min(ch.levels[c], len(T.XP[T.table(ch, c)])) - 1]
                        for c in T.classes(ch))
    ch.book = [s for s in ch.memorised if s]
    ch.npc, ch.morale = True, morale
    ch.icon = {'monster': mid, 'area': getattr(world.files, 'area', None), 'size': 2,
               'head': 0, 'body': 0, 'colours': bytes(6)}
    types = world.files.item_types()
    ch.calibrate(types)
    return ch
