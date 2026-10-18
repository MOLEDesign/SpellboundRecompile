"""Memorising spells: slots per spell level, the spellbook, the moons of Krynn.

Clerics and mages memorise spells into slots that depend on their level
(AD&D tables), clerics get extra slots for high wisdom, and Krynn's mages
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

# caster level -> slots for spell levels 1, 2, 3 ...
MAGE_SLOTS = {1: (1,), 2: (2,), 3: (2, 1), 4: (3, 2), 5: (4, 2, 1), 6: (4, 2, 2), 7: (4, 3, 2, 1),
              8: (4, 3, 3, 2), 9: (4, 3, 3, 2, 1), 10: (4, 4, 3, 2, 2), 11: (4, 4, 4, 3, 3),
              12: (4, 4, 4, 4, 4)}
CLERIC_SLOTS = {1: (1,), 2: (2,), 3: (2, 1), 4: (3, 2), 5: (3, 3, 1), 6: (3, 3, 2), 7: (3, 3, 2, 1),
                8: (3, 3, 3, 2), 9: (4, 4, 3, 2, 1), 10: (4, 4, 3, 3, 2), 11: (5, 4, 4, 3, 2),
                12: (6, 5, 5, 3, 2)}
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


def caster_levels(ch):
    lv = ch.levels
    return {CLERIC: max(lv.get('cleric', 0), lv.get('paladin', 0) - 8),
            MAGE: max(lv.get('magic-user', 0), lv.get('ranger', 0) - 8)}


def slots(ch, day=0):
    """{(class, spell level): slots} plus (MAGE, 'bonus') for the moon's gift."""
    out = {}
    levels = caster_levels(ch)
    if levels[CLERIC] > 0:
        base = CLERIC_SLOTS[min(12, levels[CLERIC])]
        bonus = WIS_BONUS.get(min(18, ch.stats.get('WIS', 0)), ())
        for i, n in enumerate(base):
            out[(CLERIC, i + 1)] = n + (bonus[i] if i < len(bonus) else 0)
    if levels[MAGE] > 0:
        for i, n in enumerate(MAGE_SLOTS[min(12, levels[MAGE])]):
            out[(MAGE, i + 1)] = n
        extra = moon_effect(ch, day)[1]
        if extra:
            out[(MAGE, 'bonus')] = extra
    return out


def known(ch):
    """Spell ids the character can choose to memorise, by class: {'C': [...], 'M': [...]}"""
    sl = slots(ch)
    top = {cls: max([lvl for (c, lvl) in sl if c == cls and lvl != 'bonus'] or [0]) for cls in (CLERIC, MAGE)}
    out = {CLERIC: [], MAGE: []}
    for sid, sp in sorted(SPELLS.items()):
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
    free = dict(slots(ch, day))
    kept, dropped = [], []
    for sid in wanted:
        sp = SPELLS.get(sid)
        if sp is None:
            dropped.append(sid)
            continue
        key = (sp.cls, sp.level)
        if free.get(key, 0) > 0:
            free[key] -= 1
            kept.append(sid)
        elif sp.cls == MAGE and free.get((MAGE, 'bonus'), 0) > 0 and (MAGE, sp.level) in free:
            free[(MAGE, 'bonus')] -= 1
            kept.append(sid)
        else:
            dropped.append(sid)
    return kept, dropped


def used(ch, wanted, day=0):
    """{(class, level or 'bonus'): slots taken} by a selection (for the screen)."""
    free = dict(slots(ch, day))
    out = {k: 0 for k in free}
    for sid in fit(ch, wanted, day)[0]:
        sp = SPELLS[sid]
        key = (sp.cls, sp.level)
        if out[key] < free[key]:
            out[key] += 1
        else:
            out[(MAGE, 'bonus')] += 1
    return out
