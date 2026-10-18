"""Monsters' special abilities, turning undead, and lasting ailments.

MONnSPC.DAX: for each special monster, a chain of 9-byte affect records
(affect code, duration u16, data, flag, link to the next). The codes the
game uses, read from which monsters carry them:

    0x18 breath weapon (every dragon; the next code says which)
    0x68 fire (red)  0x53 cold (white)  0x5A acid (black)  0x55 lightning (blue)
    0x54 poison gas (green)  0x06 cold (Maya, the silver dragon)
    0x49 dragon fear
    0x43 baaz: turns to stone when slain   0x44 bozak: its bones explode
    0x45 paralysing touch (kapak saliva, ghasts)   0x46 kapak: dissolves in acid
    0x58 ghoul's paralysing touch (elves are immune)   0x4F ghast's stench
    0x60 undead: sleep, charm, hold, fear and confusion do not work
    0x40 giant snake's poison   0x41 giant centipede's poison

The engine's affect table is not decoded yet, so what each does follows the
AD&D and Dragonlance rules the codes point to; the numbers are here to tune.
"""
from .combat import roll
from .spells import SPELLS, Spell

BREATH = 0x18
BREATHS = {0x68: ('fire', 'cone'), 0x53: ('frost', 'cone'), 0x5A: ('acid', 'line'),
           0x55: ('lightning', 'line'), 0x54: ('poison gas', 'cone'), 0x06: ('frost', 'cone')}
FEAR, STONE, BONES, PARALYSE, ACID, GHOUL, STENCH, UNDEAD = 0x49, 0x43, 0x44, 0x45, 0x46, 0x58, 0x4F, 0x60
VENOM = {0x40: (2, 6), 0x41: (1, 6)}
UNDEAD_NAMES = ('SKELET', 'ZOMBIE', 'GHOUL', 'GHAST', 'WIGHT', 'WRAITH', 'SPECTR', 'GHOST', 'MUMMY',
                'VAMPIRE', 'LICH', 'DEATH KNIGHT', 'SHADOW')
IMMUNE_UNDEAD = ('asleep', 'held', 'charmed', 'afraid', 'confused', 'nauseated')


def read_specials(world, mid, area):
    """The affect codes of a monster (empty when it has none)."""
    c, _ = world.files.find('mon', mid, ('spc.dax',), prefer=area)
    if c is None or mid not in c:
        return set()
    d = c.get(mid)
    return {d[k] for k in range(0, len(d) - 8, 9) if d[k]}


# --- breath weapons, as spells the dragon "casts" ------------------------------------
def _breath_effect(b, c, t, sp, lv):
    dmg = max(1, c.hp)                                  # AD&D: as much as the dragon's hit points
    if b.rng.randint(1, 20) + t.mod('save') >= t.save_spell:
        dmg = max(1, dmg // 2)
        b.damage(t, dmg, '%s dodges part of the %s: %d damage.' % (t.name, sp.name.lower(), dmg))
    else:
        b.damage(t, dmg, '%s is caught in the %s: %d damage.' % (t.name, sp.name.lower(), dmg))


BREATH_SPELLS = {}
for k, (code, (what, shape)) in enumerate(sorted(BREATHS.items())):
    sid = 200 + k
    sp = Spell(sid, 'Dragon %s' % what.title(), 'M', 4, shape, 0, 0, _breath_effect,
               length=6 if shape == 'cone' else 10)
    SPELLS[sid] = BREATH_SPELLS[code] = sp


def arm(c, codes, name):
    """Give a monster combatant its specials."""
    c.specials = set(codes)
    c.undead = UNDEAD in codes or any(w in name.upper() for w in UNDEAD_NAMES)
    if BREATH in codes:
        kind = next((k for k in codes if k in BREATHS), 0x68)
        c.spells = list(c.spells) + [BREATH_SPELLS[kind].id] * 3      # three breaths a day


# --- hooks the battle calls -------------------------------------------------------------
def on_hit(b, a, d):
    """After a's blow lands on d: paralysis and venom."""
    sp = getattr(a, 'specials', ())
    if not sp or not d.active:
        return
    elf = getattr(d, 'ref', None) is not None and len(d.ref.raw) > 0x5B and d.ref.raw[0x5B] in (0, 1, 2)
    if (PARALYSE in sp or (GHOUL in sp and not elf)) and not d.has('held'):
        if b.rng.randint(1, 20) + d.mod('save') < d.save_spell:
            d.conditions['held'] = b.rng.randint(2, 6)
            b.log('%s is paralysed!' % d.name)
    for code, (n, size) in VENOM.items():
        if code in sp and b.rng.randint(1, 20) + d.mod('save') < d.save_spell:
            dmg = roll(b.rng, n, size)
            b.damage(d, dmg, '%s is poisoned: %d more damage.' % (d.name, dmg))
            ail(d, 'poisoned')


def on_death(b, d):
    """A draconian's death throes."""
    sp = getattr(d, 'specials', ())
    name = d.name.upper()
    if STONE in sp or 'BAAZ' in name:
        b.log('%s turns to stone.' % d.name)
    if BONES in sp or 'BOZAK' in name:
        b.log("%s's bones explode!" % d.name)
        for o in list(b.all):
            if o is not d and o.present and b.distance(o, d) <= 1:
                dmg = roll(b.rng, 1, 6)
                if b.rng.randint(1, 20) >= o.save_spell:
                    dmg //= 2
                if dmg:
                    b.damage(o, dmg, '%s is hit by bone splinters for %d.' % (o.name, dmg))
    if ACID in sp or 'KAPAK' in name:
        b.log('%s dissolves into a pool of acid.' % d.name)
        for o in list(b.all):
            if o is not d and o.present and b.distance(o, d) <= 1:
                b.damage(o, roll(b.rng, 1, 6), '%s is splashed with acid.' % o.name)


def at_start(b):
    """Before the first round: dragon fear."""
    for m in b.enemies:
        if FEAR in getattr(m, 'specials', ()):
            for p in b.party:
                if p.active and p.hd < m.hd and b.rng.randint(1, 20) + p.mod('save') < p.save_spell:
                    p.conditions['afraid'] = b.rng.randint(2, 5)
                    b.log('%s quails before %s!' % (p.name, m.name))


def each_round(b):
    """Ghasts' stench sickens those next to them."""
    for m in b.enemies:
        if STENCH in getattr(m, 'specials', ()) and m.active:
            for p in b.party:
                if p.active and b.adjacent(m, p) and not any(e[0] == 'Stench' for e in p.effects):
                    if b.rng.randint(1, 20) < p.save_spell:
                        p.effects.append(['Stench', 2, {'hit': -2}])
                        b.log('%s retches at the stench.' % p.name)


def immune(t, cond):
    return getattr(t, 'undead', False) and cond in IMMUNE_UNDEAD


# --- turning undead ----------------------------------------------------------------------
def turn_level(c):
    """A cleric's (or paladin's) turning level; Majere's clerics turn as two higher."""
    ref = getattr(c, 'ref', None)
    if ref is None:
        return 0
    lv = max(ref.levels.get('cleric', 0), ref.levels.get('paladin', 0) - 2)
    if lv and len(ref.raw) > 0x5E and ref.raw[0x5E] == 2:
        lv += 2
    return lv


def turn_undead(b, c):
    """c presents a holy symbol: undead near by flee, the weak are destroyed.
    d20 against 7 + 3 x (hit dice - level); 2d6 hit dice of undead in all."""
    lv = turn_level(c)
    c.attacked = True
    c.half_moves = 0
    undead = sorted([e for e in b.foes(c) if getattr(e, 'undead', False) and b.distance(c, e) <= 6],
                    key=lambda e: (e.hd, b.distance(c, e)))
    if not undead:
        b.log('%s raises a holy symbol, but no undead are near.' % c.name)
        return []
    r = b.rng.randint(1, 20)
    budget = roll(b.rng, 2, 6)
    hit = []
    for e in undead:
        need = 7 + 3 * (e.hd - lv)
        if need > 20 or r < need or e.hd > budget:
            continue
        budget -= e.hd
        if lv - e.hd >= 4:
            b.damage(e, e.hp + 10, '%s crumbles to dust before %s!' % (e.name, c.name))
        else:
            e.conditions['fleeing'] = 999
            b.log('%s is turned and flees!' % e.name)
        hit.append(e)
    if not hit:
        b.log('%s raises a holy symbol; the undead stand firm.' % c.name)
    return hit


# --- lasting ailments (outside combat too) -----------------------------------------------
AILMENTS = {'poisoned': {'hit': -1}, 'diseased': {'hit': -2, 'dmg': -1}, 'blind': {'hit': -4, 'ac': -4}}
CURES = {26: 'poisoned', 59: 'poisoned', 39: 'diseased', 37: 'blind'}


def ail(combatant, name):
    """Mark a party member's lasting ailment (it outlasts the fight)."""
    ref = getattr(combatant, 'ref', None)
    if ref is not None:
        ref.ailments = set(getattr(ref, 'ailments', ())) | {name}
    if not any(e[0] == name for e in combatant.effects):
        combatant.effects.append([name, 999, dict(AILMENTS[name])])


def ailment_effects(ch):
    return [[name, 999, dict(AILMENTS[name])] for name in sorted(getattr(ch, 'ailments', ()))]

