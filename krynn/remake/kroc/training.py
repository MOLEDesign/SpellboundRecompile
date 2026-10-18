"""Experience, training and level limits, from the manual's tables (pp. 56-58).

A character has one experience total and every class counts it in full (a
fighter/mage with 5,000 XP is a third-level fighter and a second-level
mage). Experience a multi-class character earns is shared out between the
classes, as in AD&D.

Training is free in a hall. Each class with enough experience goes up one
level: hit points (one hit die, plus constitution), THAC0, saving throws
and spell slots improve, and a mage chooses a new spell for the grimoire.

The original made a character who had earned two levels between visits
lose the experience beyond the first; the remake keeps it, so training
again goes up the next level too.

Character record: 0x5B race (0 Silvanesti, 1 Qualinesti, 2 half-elf,
3 mountain dwarf, 4 hill dwarf, 5 kender, 6 human), 0x5C class combination,
0x5D knightly order (1 Crown, 2 Sword, 3 Rose), 0x5E deity (1 Paladine,
2 Majere, 3 Kiri-Jolith, 4 Mishakal: good; 5 Sirrion, 6 Reorx, 7 Shinare:
neutral), 0x5F mage order (1 White, 2 Red, 3 Black).
"""
from . import magic
from .spells import SPELLS

RACES = ('Silvanesti elf', 'Qualinesti elf', 'half-elf', 'mountain dwarf', 'hill dwarf', 'kender', 'human')

# least experience for levels 1, 2, 3 ... of each table
XP = {
    'fighter': (0, 2001, 4001, 8001, 18001, 35001, 70001, 125001),
    'ranger': (0, 2251, 4501, 10001, 20001, 40001, 90001),
    'thief': (0, 1251, 2501, 5001, 10001, 20001, 42501, 70001, 110001),
    'crown': (0, 5000, 10000, 18500, 37000, 85000, 140000, 220000),
    'sword': (0, 0, 12000, 24000, 45000, 95000, 175000, 350000),
    'rose': (0, 0, 0, 27000, 66000, 125000, 200000, 425000),
    'white': (0, 5000, 10000, 20000, 38000, 55000, 100000, 200000),
    'red': (0, 5000, 10000, 18000, 36000, 50000, 90000, 180000),
    'good': (0, 4000, 7500, 15250, 25000, 40000, 90000, 160000),
    'neutral': (0, 3000, 6000, 13000, 27500, 55000, 110000, 225000),
}
HIT_DIE = {'fighter': 10, 'paladin': 10, 'knight': 10, 'ranger': 8, 'cleric': 8, 'druid': 8,
           'thief': 6, 'magic-user': 4}
FIGHTERS = ('fighter', 'paladin', 'ranger', 'knight')

# maximum level by class (and prime requisite) for human, Silvanesti, Qualinesti,
# half-elf, hill dwarf, mountain dwarf, kender; None = not open to that race
_ = None
LIMITS = {
    'cleric': {0: (8, 8, 8, 8, 8, 8, 8)},
    'fighter': {16: (8, 8, 8, 8, 8, 8, 5), 17: (8, 8, 8, 8, 8, 8, 6), 18: (8, 8, 8, 8, 8, 8, 7)},
    'ranger': {16: (7, 7, 7, 7, 7, _, 5), 17: (7, 7, 7, 7, 7, _, 6), 18: (7, 7, 7, 7, 7, _, 7)},
    'knight': {0: (8, _, _, 8, _, _, _)},
    'magic-user': {0: (8, 8, 8, 8, _, _, _)},
    'thief': {0: (9, _, 9, 9, 9, 8, 9)},
}
COLUMN = {6: 0, 0: 1, 1: 2, 2: 3, 4: 4, 3: 5, 5: 6}       # race byte -> column above


def _byte(ch, off):
    return ch.raw[off] if len(ch.raw) > off else 0


def table(ch, cls):
    """The advancement table a class of this character follows."""
    if cls == 'knight':
        return ('crown', 'sword', 'rose')[max(0, min(2, _byte(ch, 0x5D) - 1))]
    if cls == 'magic-user':
        return 'red' if _byte(ch, 0x5F) in (2, 3) else 'white'
    if cls in ('cleric', 'druid'):
        return 'neutral' if _byte(ch, 0x5E) >= 5 else 'good'
    if cls == 'paladin':
        return 'fighter'
    return cls


def classes(ch):
    return [c for c, lv in ch.levels.items() if lv]


def limit(ch, cls):
    rows = LIMITS.get(cls)
    if rows is None:
        return 8
    stat = ch.stats.get('STR' if cls in ('fighter', 'ranger') else 'INT', 0)
    key = 0 if 0 in rows else max([k for k in rows if k <= max(16, min(18, stat))] or [16])
    return rows[key][COLUMN.get(_byte(ch, 0x5B), 0)] or 0


def next_level_xp(ch, cls):
    """Experience needed for the next level of a class, or None at the top."""
    lv = ch.levels[cls]
    xp = XP[table(ch, cls)]
    if lv >= len(xp) or lv >= limit(ch, cls):
        return None
    return xp[lv]


def ready(ch):
    """Classes that can go up a level now."""
    out = []
    for cls in classes(ch):
        need = next_level_xp(ch, cls)
        if need is not None and ch.experience >= need:
            out.append(cls)
    return out


def share(ch, xp):
    """What a character gets of an experience award (split between classes)."""
    return xp // max(1, len(classes(ch)))


# --- what a level brings ----------------------------------------------------------------
def thac0_for(levels):
    """The best THAC0 of a set of class levels (AD&D first-edition matrices)."""
    best = 21
    for cls, lv in levels.items():
        if not lv:
            continue
        if cls in FIGHTERS:
            v = 20 - 2 * ((lv - 1) // 2)
        elif cls in ('cleric', 'druid'):
            v = 20 - 2 * ((lv - 1) // 3)
        elif cls == 'thief':
            v = 21 - 2 * ((lv - 1) // 4)
        else:
            v = 21 - 2 * ((lv - 1) // 5)
        best = min(best, v)
    return best


def con_bonus(con, cls):
    if con <= 3:
        return -2
    if con <= 6:
        return -1
    if con <= 14:
        return 0
    if con == 15:
        return 1
    if cls in FIGHTERS:
        return {16: 2, 17: 3}.get(con, 4)
    return 2


def roll_hp(ch, cls, rng):
    """One hit die for the new level; never less than half the die (the remake
    spares you the original's 1-point levels)."""
    die = HIT_DIE.get(cls, 8)
    return max(rng.randint(1, die), (die + 1) // 2) + con_bonus(ch.stats.get('CON', 10), cls)


def train(ch, rng):
    """Advance every class that is ready by one level. Returns the lines to show."""
    up = ready(ch)
    if not up:
        return []
    old = dict(ch.levels)
    n = len(classes(ch))
    gain = 0
    for cls in up:
        ch.levels[cls] += 1
        gain += roll_hp(ch, cls, rng)
        if cls == 'magic-user':
            ch.spell_picks += 1
    gain = max(1, -(-gain // n))                     # multi-class: shared out
    ch.hp_max += gain
    ch.hp += gain
    ch.base_thac0 += thac0_for(ch.levels) - thac0_for(old)
    names = ', '.join('%s %d' % (c, ch.levels[c]) for c in up)
    lines = ['%s is now %s: +%d hit points.' % (ch.name, names, gain)]
    if ch.spell_picks:
        lines.append('%s may add a spell to the grimoire.' % ch.name)
    return lines


# --- the grimoire ---------------------------------------------------------------------
# which first- to fourth-level mage spells each order may learn (manual pp. 54-55)
WHITE = {10, 11, 14, 15, 16, 18, 19, 21, 29, 33, 34, 46, 47, 49, 51, 52, 54, 73, 74, 77, 78, 79, 80, 81}
RED = {9, 11, 12, 15, 18, 19, 20, 29, 30, 31, 32, 34, 35, 45, 47, 48, 50, 51, 55, 75, 76, 77, 79}


def learnable(ch, day=0):
    """Mage spells this character may add to the grimoire now."""
    allowed = RED if _byte(ch, 0x5F) in (2, 3) else WHITE
    top = max([lvl for (c, lvl) in magic.slots(ch, day) if c == magic.MAGE and lvl != 'bonus'] or [0])
    return [s for s in sorted(allowed) if SPELLS[s].level <= top and s not in ch.book]
