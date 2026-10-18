"""Memorising spells: slots per spell level, the spellbook, the moons of Krynn.

Clerics and mages memorise spells into slots that depend on their level
(Krynn's tables, which differ by mage order and by the cleric's god),
clerics get extra slots for high wisdom, and Krynn's mages
get extra spells while their order's moon waxes (manual, The Moons of
Magic):

    moon phase      saving throws   extra spells   effective level
    low sanction        -1              0               -1
    waning              normal          0               even
    waxing              normal          +1              even
    high sanction       +1              +2              +1 (level 6+, INT 15+)

The extra ("bonus") spells may be of any level the mage can cast. White
Robes follow Solinari (36-day cycle), Red Robes Lunitari (28 days), Black
Robes Nuitari (8 days); the game starts with Solinari and Lunitari full,
which is why the starting mages have two first-level spells more than the
AD&D table gives them.

Character record: 0x5F mage order (1 white, 2 red, 3 black, 0 none);
0x66-0xC3 one byte per spell number (0x65 + id), set when the spell is in
the mage's grimoire or the cleric's list.
"""
from .spells import SPELLS

CLERIC, MAGE = 'C', 'M'

# Krynn's own tables (manual pp. 57-58): level -> slots for spell levels 1, 2, 3, 4
SLOTS = {
    'white': ((1,), (2,), (2, 1), (3, 2), (4, 2, 1), (4, 2, 2), (4, 3, 2, 1), (4, 3, 3, 2)),
    'red': ((1,), (2,), (2, 1), (3, 2, 1), (4, 3, 1), (4, 3, 2), (4, 3, 2, 1), (4, 3, 3, 2)),
    'good': ((1,), (2,), (2, 1), (2, 2), (3, 3, 1), (3, 3, 2), (3, 3, 2, 1), (3, 3, 3, 2)),
    'neutral': ((2,), (2, 1), (3, 2, 1), (4, 2, 2), (4, 3, 2), (4, 3, 2, 1), (4, 4, 3, 1), (4, 4, 3, 2)),
    # knights of the Sword and the Rose pray for cleric spells from level 6
    'knight': ((), (), (), (), (), (1,), (2,), (2, 1)),
}


def _table(levels, row):
    return levels[min(len(levels), row) - 1] if row > 0 else ()
WIS_BONUS = {13: (1,), 14: (2,), 15: (2, 1), 16: (2, 2), 17: (2, 2, 1), 18: (2, 2, 1, 1)}

# reversed (evil) cleric spells, druid spells and the scroll/item duplicates
# are not memorised by the player characters of this game
EVIL = {2, 4, 7, 38, 40, 44, 58, 60, 64, 68}
DRUID = {69, 70, 71, 72}
DUPLICATE = set(range(87, 95))

MOONS = {1: ('Solinari', 36), 2: ('Lunitari', 28), 3: ('Nuitari', 8)}
PHASES = ('high sanction', 'waning', 'low sanction', 'waxing')
PHASE_EFFECT = {   # (save bonus, extra spells, level bonus)
    'high sanction': (1, 2, 1), 'waning': (0, 0, 0), 'low sanction': (-1, 0, -1), 'waxing': (0, 1, 0)}


def moon_phase(order, day):
    """Phase of the moon governing mage order 1-3 on a given day (day 0: full)."""
    if order not in MOONS:
        return None
    cycle = MOONS[order][1]
    return PHASES[int(4 * (day % cycle) / cycle)]


def moon_effect(ch, day):
    """(save bonus, extra spells, level bonus) the moon gives this mage today."""
    if not ch.levels.get('magic-user'):
        return 0, 0, 0
    phase = moon_phase(ch.raw[0x5F] if len(ch.raw) > 0x5F else 0, day)
    if phase is None:
        return 0, 0, 0             # rogue mages get nothing from the moons
    save, extra, level = PHASE_EFFECT[phase]
    if level > 0 and not (ch.levels['magic-user'] >= 6 and ch.stats.get('INT', 0) >= 15):
        level = 0
    return save, extra, level


def knight_casts(ch):
    return ch.levels.get('knight', 0) >= 6 and len(ch.raw) > 0x5D and ch.raw[0x5D] in (2, 3)


def caster_levels(ch):
    lv = ch.levels
    knight = lv.get('knight', 0) - 5 if knight_casts(ch) else 0
    return {CLERIC: max(lv.get('cleric', 0), lv.get('paladin', 0) - 8, knight),
            MAGE: max(lv.get('magic-user', 0), lv.get('ranger', 0) - 8)}


def slots(ch, day=0):
    """{(class, spell level): slots} plus (MAGE, 'bonus') for the moon's gift."""
    from .training import table
    out = {}
    lv = ch.levels
    if lv.get('cleric') or lv.get('druid'):
        base = _table(SLOTS[table(ch, 'cleric')], max(lv.get('cleric', 0), lv.get('druid', 0)))
    elif knight_casts(ch):
        base = _table(SLOTS['knight'], lv['knight'])
    else:
        base = ()
    if base:
        bonus = WIS_BONUS.get(min(18, ch.stats.get('WIS', 0)), ())
        for i, n in enumerate(base):
            out[(CLERIC, i + 1)] = n + (bonus[i] if i < len(bonus) else 0)
    if lv.get('magic-user'):
        for i, n in enumerate(_table(SLOTS[table(ch, 'magic-user')], lv['magic-user'])):
            out[(MAGE, i + 1)] = n
        extra = moon_effect(ch, day)[1]
        if extra:
            out[(MAGE, 'bonus')] = extra
    cleric = max(lv.get('cleric', 0), lv.get('druid', 0))
    if cleric and specials(ch):
        out[(CLERIC, 'special')] = 1 + (cleric >= 5)
    return out


# The gods' gifts to their clerics (manual p.17): special spells, memorised in
# their own slots (one, two from fifth level), and a power or two
GOD_SPELLS = {1: (88,), 2: (89,), 3: (90,), 4: (93, 91, 92), 5: (94,), 6: (), 7: (93,)}
GODS = {1: 'Paladine', 2: 'Majere', 3: 'Kiri-Jolith', 4: 'Mishakal', 5: 'Sirrion', 6: 'Reorx', 7: 'Shinare'}


def deity(ch):
    if not (ch.levels.get('cleric') or ch.levels.get('druid')) or len(ch.raw) <= 0x5E:
        return 0
    return ch.raw[0x5E]


def specials(ch):
    return GOD_SPELLS.get(deity(ch), ())


def god_hit_bonus(ch):
    """Kiri-Jolith's clerics, and Reorx's dwarves, fight one better."""
    d = deity(ch)
    race = ch.raw[0x5B] if len(ch.raw) > 0x5B else 6
    return 1 if d == 3 or (d == 6 and race in (3, 4)) else 0


def heal_bonus_dice(ch):
    """Mishakal's clerics roll one more die on every healing spell."""
    return 1 if deity(ch) == 4 else 0


def known(ch):
    """Spell ids the character can choose to memorise, by class: {'C': [...], 'M': [...]}"""
    sl = slots(ch)
    top = {cls: max([lvl for (c, lvl) in sl if c == cls and isinstance(lvl, int)] or [0])
           for cls in (CLERIC, MAGE)}
    out = {CLERIC: [], MAGE: []}
    for sid, sp in sorted(SPELLS.items()):
        if sid in specials(ch) and (CLERIC, 'special') in sl:
            out[CLERIC].append(sid)        # the god's own gift
            continue
        if sid in DUPLICATE or sid in DRUID or sp.level > top[sp.cls]:
            continue
        if sp.cls == CLERIC and sid not in EVIL:
            out[CLERIC].append(sid)        # clerics may pray for any spell of their levels
        elif sp.cls == MAGE and sid in ch.book:
            out[MAGE].append(sid)          # mages only what is in their grimoire
    return out


def fit(ch, wanted, day=0):
    """The longest prefix-preserving selection of `wanted` that fits the slots.

    Mage spells beyond their level's slots go into the moon's bonus slots.
    Returns (kept, dropped)."""
    placed = _assign(ch, wanted, day)
    return [s for s, k in placed if k], [s for s, k in placed if not k]


def _assign(ch, wanted, day):
    """[(spell, slot key or None)] in order: the slot each wanted spell takes."""
    free = dict(slots(ch, day))
    gifts = specials(ch)
    out = []
    for sid in wanted:
        sp = SPELLS.get(sid)
        key = None
        if sp is None:
            pass
        elif sid in gifts and free.get((CLERIC, 'special'), 0) > 0:
            key = (CLERIC, 'special')
        elif sid not in gifts and free.get((sp.cls, sp.level), 0) > 0:
            key = (sp.cls, sp.level)
        elif sp.cls == MAGE and free.get((MAGE, 'bonus'), 0) > 0 and (MAGE, sp.level) in free:
            key = (MAGE, 'bonus')
        if key:
            free[key] -= 1
        out.append((sid, key))
    return out


def used(ch, wanted, day=0):
    """{(class, level or 'bonus'): slots taken} by a selection (for the screen)."""
    out = {k: 0 for k in slots(ch, day)}
    for _, key in _assign(ch, wanted, day):
        if key:
            out[key] += 1
    return out
