"""Making new characters, by the manual's rules (pp. 12-17, 55-58).

A character is built as a 426-byte record in the save disk's layout, so
everything else in the remake (training, spells, items, saves) treats it
like the characters from the save disk.

Rules the remake chooses where the manual is silent or the original was
harsh: abilities are rolled 4d6, best three, inside the race's limits, as
often as you like; hit points start at the hit die's average or better.
"""
from cok.items import Item

from . import magic, training as T
from .world import Character

CLASSES = ('cleric', 'druid', 'fighter', 'paladin', 'ranger', 'magic-user', 'thief', 'knight')
# class combinations in the executable's order (record byte 0x5C)
COMBOS = (('cleric',), ('druid',), ('fighter',), ('paladin',), ('ranger',), ('magic-user',), ('thief',),
          ('knight',), ('cleric', 'fighter'), ('cleric', 'fighter', 'magic-user'), ('cleric', 'ranger'),
          ('cleric', 'magic-user'), ('cleric', 'thief'), ('fighter', 'magic-user'), ('fighter', 'thief'),
          ('fighter', 'magic-user', 'thief'), ('magic-user', 'thief'))
PLAYABLE = ('cleric', 'fighter', 'ranger', 'knight', 'magic-user', 'thief')
STATS = ('STR', 'INT', 'WIS', 'DEX', 'CON', 'CHA')
# ability ranges by race (manual p.56; men's strength limit; percentile for 18 in RANGE18)
RANGES = {
    6: ((3, 18), (3, 18), (3, 18), (3, 18), (3, 18), (3, 18)),       # human
    0: ((3, 18), (10, 18), (6, 18), (7, 19), (6, 18), (12, 18)),     # Silvanesti
    1: ((7, 18), (8, 18), (6, 18), (7, 19), (7, 18), (8, 18)),       # Qualinesti
    2: ((3, 18), (4, 18), (3, 18), (6, 18), (6, 18), (3, 18)),       # half-elf
    3: ((8, 18), (3, 18), (3, 18), (3, 17), (12, 19), (3, 16)),      # mountain dwarf
    4: ((9, 18), (3, 18), (3, 18), (3, 17), (14, 19), (3, 12)),      # hill dwarf
    5: ((6, 16), (6, 18), (3, 16), (8, 19), (10, 18), (6, 18)),      # kender
}
RANGE18 = {6: 100, 0: 75, 1: 75, 2: 90, 3: 99, 4: 99, 5: 0}
# least ability scores for each class (AD&D; knights: manual p.13 for the Crown)
MINIMUM = {'cleric': {'WIS': 9}, 'fighter': {'STR': 9, 'CON': 7}, 'ranger': {'STR': 13, 'INT': 13, 'WIS': 14, 'CON': 14},
           'magic-user': {'INT': 9, 'DEX': 6}, 'thief': {'DEX': 9},
           'knight': {'STR': 10, 'WIS': 10, 'CON': 10}}
ALIGNMENTS = ('Lawful Good', 'Neutral Good', 'Chaotic Good', 'Lawful Neutral', 'True Neutral', 'Chaotic Neutral')
GOOD = (0, 1, 2)
GOD_NAMES = ('Paladine', 'Majere', 'Kiri-Jolith', 'Mishakal', 'Sirrion', 'Reorx', 'Shinare')
# a starting mage's grimoire, by robe
GRIMOIRE = {1: (11, 15, 18, 19, 21), 2: (9, 11, 12, 15, 18)}
# strength: (to hit, damage); 18/xx for fighters by percentile (manual p.56)
STRENGTH = {3: (-3, -1), 4: (-2, -1), 5: (-2, -1), 6: (-1, 0), 7: (-1, 0), 16: (0, 1), 17: (1, 1), 18: (1, 2)}
EXCEPTIONAL = ((50, 1, 3), (75, 2, 3), (90, 2, 4), (99, 2, 5), (100, 3, 6))


def races_for(combo):
    """Races that may take this class combination (level limits table)."""
    out = []
    for race in range(7):
        if race == 6 and len(combo) > 1:
            continue                                   # humans take one class
        ok = True
        for cls in combo:
            rows = T.LIMITS.get(cls)
            if rows is None:
                ok = False
                break
            if not any(r[T.COLUMN[race]] for r in rows.values()):
                ok = False
        if ok and 'knight' in combo and len(combo) > 1:
            ok = False
        if ok:
            out.append(race)
    return out


def combos_for(race):
    return [c for c in COMBOS if all(k in PLAYABLE for k in c) and race in races_for(c)]


def alignments_for(combo, race=6):
    if 'knight' in combo:
        return [0]                                     # knights of Solamnia: lawful good
    if 'cleric' in combo and race in (3, 4):
        return [3, 4, 5]                               # Reorx's clerics are neutral
    return list(range(len(ALIGNMENTS)))


def gods_for(alignment, race=6):
    """Gods a cleric of this alignment may serve (1-4 good, 5-7 neutral);
    dwarven clerics all serve Reorx (manual p.17)."""
    if race in (3, 4):
        return [6]
    return [1, 2, 3, 4] if alignment in GOOD else [5, 6, 7]


def roll_stats(rng, race, combo):
    """4d6 best three for each ability, kept inside the race's limits."""
    out = {}
    for s, (lo, hi) in zip(STATS, RANGES[race]):
        dice = sorted(rng.randint(1, 6) for _ in range(4))
        out[s] = max(lo, min(hi, sum(dice[1:])))
    fighter = any(c in ('fighter', 'ranger', 'knight') for c in combo)
    out['STR18'] = rng.randint(1, RANGE18[race]) if out['STR'] == 18 and fighter and RANGE18[race] else 0
    return out


def qualifies(stats, combo):
    """The abilities a class combination needs and these lack ([] when fine)."""
    short = []
    for cls in combo:
        for s, need in MINIMUM.get(cls, {}).items():
            if stats[s] < need and s not in short:
                short.append(s)
    return short


def strength_bonus(stats, combo):
    st = stats['STR']
    if st == 18 and stats.get('STR18') and any(c in ('fighter', 'ranger', 'knight') for c in combo):
        p = stats['STR18']
        return next((h, d) for top, h, d in EXCEPTIONAL if p <= top)
    return STRENGTH.get(st, (0, 0))


def start_xp(cls, alignment):
    """Experience a new character starts with: second level, but clerics and knights first."""
    if cls == 'cleric':
        return 2000 if alignment in GOOD else 1500
    if cls == 'knight':
        return 2500
    return {'fighter': 2001, 'ranger': 2251, 'thief': 1251, 'magic-user': 5000}[cls]


def level_for(ch, cls):
    xp = T.XP[T.table(ch, cls)]
    return max([lv for lv in range(1, len(xp) + 1) if ch.experience >= xp[lv - 1]] or [1])


# --- starting kit ----------------------------------------------------------------------
def _item(name, type_, words, weight, value, quantity=1, ready=True):
    return Item(name, type_, ready, quantity, words, 0, 0, False, weight, value)


KIT = {
    'knight': [('Plate Mail', 36, (0, 0x2f, 0x24), 450, 40), ('Shield', 37, (0, 0, 37), 100, 1),
               ('Long Sword', 18, (0, 0, 18), 45, 7)],
    'fighter': [('Ring Mail', 32, (0, 0x2f, 0x20), 250, 8), ('Shield', 37, (0, 0, 37), 100, 1),
                ('Long Sword', 18, (0, 0, 18), 45, 7), ('Short Bow', 25, (0, 0, 25), 10, 10),
                ('Arrows', 30, (0, 0, 30), 4, 0, 40)],
    'ranger': [('Ring Mail', 32, (0, 0x2f, 0x20), 250, 8), ('Long Sword', 18, (0, 0, 18), 45, 7),
               ('Long Bow', 24, (0, 0, 24), 10, 20), ('Arrows', 30, (0, 0, 30), 4, 0, 40)],
    'cleric': [('Ring Mail', 32, (0, 0x2f, 0x20), 250, 8), ('Shield', 37, (0, 0, 37), 100, 1),
               ('Mace', 8, (0, 0, 8), 60, 2), ('Staff Sling', 29, (0, 0x1c, 0x1d), 20, 0)],
    'thief': [('Leather Armor', 31, (0, 0x30, 0x1f), 150, 1), ('Short Sword', 19, (0, 0, 19), 35, 3),
              ('Sling', 28, (0, 0, 28), 5, 0)],
    'magic-user': [('Quarter Staff', 15, (0, 0, 15), 30, 1), ('Darts', 5, (0, 0, 5), 1, 0, 12)],
}
KENDER_KIT = ('Houpak', 67, (0, 0, 67), 10, 2)
ORDER = ('knight', 'fighter', 'ranger', 'cleric', 'thief', 'magic-user')     # who sets the kit


def starting_items(combo, race, types):
    """A sensible kit for the combination: armour no mage would wear is left out."""
    lead = next(c for c in ORDER if c in combo)
    kit = [_item(*k) for k in KIT[lead]]
    if race == 5:                                       # kender carry a hoopak
        kit = [i for i in kit if types[i.type].slot not in (0, 10)] + [_item(*KENDER_KIT)]
    for it in kit:                                       # one weapon in hand, the rest slung
        t = types[it.type]
        if t.slot == 0 and t.launcher:
            it.ready = False
    hand = [i for i in kit if types[i.type].slot == 0 and not types[i.type].launcher]
    for extra in hand[1:]:
        extra.ready = False
    return kit


# --- the record --------------------------------------------------------------------------
def build(name, race, combo, alignment, stats, rng, types, words, god=0, slot=0, icon=None):
    """A new Character, as a record in the save disk's layout."""
    r = bytearray(0x1AA)
    nm = name.upper().encode('latin-1')[:15]
    r[0:len(nm)] = nm
    for k, s in enumerate(STATS):
        r[0x10 + 2 * k] = r[0x11 + 2 * k] = stats[s]
    r[0x1C] = stats.get('STR18', 0)
    r[0x5B] = race
    r[0x5C] = COMBOS.index(tuple(combo))
    if 'knight' in combo:
        r[0x5D] = 1                                      # Knights of the Crown
    if 'cleric' in combo:
        r[0x5E] = god or gods_for(alignment, race)[0]
    if 'magic-user' in combo:
        r[0x5F] = 1 if alignment in GOOD else 2          # White Robes / Red Robes
    xp = max(start_xp(c, alignment) for c in combo)
    r[0x11E:0x122] = xp.to_bytes(4, 'big')
    ch = Character(name.upper(), bytes(r), starting_items(combo, race, types))
    ch.experience = xp
    for cls in combo:
        ch.levels[cls] = level_for(ch, cls)
    # hit points: each class's dice for its levels, at least half each die
    con = stats['CON']
    total = 0
    for cls in combo:
        die = T.HIT_DIE[cls]
        dice = ch.levels[cls] + (1 if cls in ('ranger', 'knight') or
                                 (cls == 'cleric' and alignment in GOOD) else 0)
        total += sum(max(rng.randint(1, die), (die + 1) // 2) + T.con_bonus(con, cls) for _ in range(dice))
    ch.hp_max = ch.hp = max(1, total // len(combo))
    ch.base_thac0 = T.thac0_for(ch.levels)
    hit, dmg = strength_bonus(stats, combo)
    ch.hit_bonus, ch.dmg_bonus = hit, dmg
    ch.alignment = alignment
    ch.move = 12
    if icon is None:
        icon = {'head': rng.randint(0, 8), 'body': rng.choice((1, 11, 14, 24, 28)),
                'colours': bytes(rng.randint(0, 255) for _ in range(6))}
    ch.icon = dict(icon, size=1 if race in (3, 4, 5) else 2)
    ch.book = list(GRIMOIRE[r[0x5F]]) if 'magic-user' in combo else []
    # memorise a first choice: cures and blessings, missiles and sleep
    want = []
    for sid in (3, 1, 3, 1) + (15, 21, 15, 21) + (92, 91, 93, 89, 88, 90, 94):
        if sid in magic.known(ch)['C'] + magic.known(ch)['M']:
            want.append(sid)
    ch.memorised = magic.fit(ch, want)[0]
    ch.spells = list(ch.memorised)
    ch.refresh(types, words)
    return ch

