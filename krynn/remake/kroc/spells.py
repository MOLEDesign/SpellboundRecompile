"""Spells in combat.

Spell numbers are the game's own (the names in the executable, 1 Bless ...
94 Burning Hands; a few numbers repeat a spell for scrolls and items).
Every spell has a shape and an effect:

    self      the caster                 party   every friend
    ally      one friend within range    enemy   one foe within range
    foes      up to N foes around a chosen square (only foes are touched)
    area      everyone within a radius of a chosen square, friend or foe
    line      a bolt from the caster towards a square
    cone      a widening cone from the caster towards a square

Area spells hit friends too, as in the original; the combat screen shows
exactly which squares and creatures a spell will hit before it is cast.
A d20 roll at or above the target's saving throw resists (halves damage or
cancels the effect). Caster level is the cleric or magic-user level for
the party and the hit dice for monsters.
"""
import math

from .combat import PARTY, OK, DEAD, FLED, Attack, roll

CLERIC, MAGE = 'C', 'M'


class Spell:
    def __init__(self, sid, name, cls, level, shape, range_=0, radius=0, effect=None,
                 combat=True, max_targets=None, length=0, note=''):
        self.id, self.name, self.cls, self.level = sid, name, cls, level
        self.shape, self.range, self.radius = shape, range_, radius
        self.effect = effect
        self.combat = combat and effect is not None
        self.max_targets = max_targets
        self.length = length
        self.note = note

    @property
    def needs_target(self):
        return self.shape not in ('self', 'party')

    @property
    def hostile(self):
        return self.shape in ('enemy', 'foes', 'area', 'line', 'cone') and self.id not in FRIENDLY_AREA


# ------------------------------------------------------------------ effects
# effect(b, caster, target, spell, level) -> None; b is the Battle

def _save(b, t, bonus=0):
    return b.rng.randint(1, 20) + t.mod('save') + bonus >= t.save_spell


def damage(n=0, size=0, plus=0, per_level=None, cap=None, save_half=True):
    def eff(b, c, t, sp, lv):
        dice = n
        if per_level:
            dice = min(cap or 99, max(1, lv // per_level[0])) * per_level[1]
        dmg = max(1, roll(b.rng, dice, size, plus))
        if save_half is not None and _save(b, t):
            if save_half:
                dmg = max(1, dmg // 2)
                b.damage(t, dmg, '%s partly resists %s: %d damage.' % (t.name, sp.name, dmg))
            else:
                b.log('%s resists %s.' % (t.name, sp.name))
            return
        b.damage(t, dmg, '%s takes %d from %s.' % (t.name, dmg, sp.name))
    return eff


def level_damage(per, cap=None, save_half=True):
    """level x dN (Fireball, Lightning Bolt: d6 per level)."""
    def eff(b, c, t, sp, lv):
        k = min(cap or 99, lv)
        dmg = max(1, roll(b.rng, k, per))
        if save_half and _save(b, t):
            dmg = max(1, dmg // 2)
            b.damage(t, dmg, '%s partly resists %s: %d damage.' % (t.name, sp.name, dmg))
            return
        b.damage(t, dmg, '%s takes %d from %s.' % (t.name, dmg, sp.name))
    return eff


def heal(n, size, plus=0):
    def eff(b, c, t, sp, lv):
        if t.status == DEAD:
            return
        extra = 0
        if getattr(c, 'ref', None) is not None and getattr(sp, 'item', None) is None:
            from .magic import heal_bonus_dice
            extra = heal_bonus_dice(c.ref)            # Mishakal's clerics
        amount = roll(b.rng, n + extra, size, plus)
        t.hp = min(t.hp_max, t.hp + amount)
        if t.status != OK and t.hp > 0:
            t.status = OK
            b.log('%s is back on their feet.' % t.name)
        b.log('%s heals %s for %d.' % (c.name, t.name, amount))
    return eff


def modify(name, rounds, **mods):
    """Timed bonus or penalty: hit, ac (better is positive), dmg, save."""
    def eff(b, c, t, sp, lv):
        r = rounds(lv) if callable(rounds) else rounds
        t.effects = [e for e in t.effects if e[0] != name]
        t.effects.append([name, r, dict(mods)])
        b.log('%s: %s.' % (t.name, sp.name))
    return eff


def condition(cond, rounds, save=True, hd_limit=None, save_bonus=0):
    def eff(b, c, t, sp, lv):
        if hd_limit is not None and t.hd > hd_limit:
            b.log('%s is too powerful for %s.' % (t.name, sp.name))
            return
        if save and _save(b, t, save_bonus):
            b.log('%s resists %s.' % (t.name, sp.name))
            return
        r = rounds(lv) if callable(rounds) else rounds
        t.conditions[cond] = max(t.conditions.get(cond, 0), r)
        b.log('%s is %s!' % (t.name, {'asleep': 'asleep', 'held': 'held fast', 'nauseated':
                                       'retching helplessly', 'slowed': 'slowed', 'hasted': 'hasted',
                                       'confused': 'confused', 'afraid': 'terrified',
                                       'silenced': 'silenced', 'invisible': 'invisible',
                                       'missile_proof': 'protected from missiles',
                                       'globe': 'inside a globe of invulnerability'}.get(cond, cond)))
    return eff


def magic_missile(b, c, t, sp, lv):
    k = max(1, (lv + 1) // 2)
    if t.has('shielded'):
        b.log("%s's shield stops the missiles." % t.name)
        return
    dmg = sum(roll(b.rng, 1, 4, 1) for _ in range(k))
    b.damage(t, dmg, '%d magic missile%s hit %s for %d.' % (k, 's' if k > 1 else '', t.name, dmg))


def burning_hands(b, c, t, sp, lv):
    b.damage(t, max(1, lv), '%s burns %s for %d.' % (c.name, t.name, max(1, lv)))


def shocking_grasp(b, c, t, sp, lv):
    dmg = roll(b.rng, 1, 8, lv)
    b.damage(t, dmg, '%s shocks %s for %d.' % (c.name, t.name, dmg))


def shield(b, c, t, sp, lv):
    modify('Shield', lambda lv: 5 * lv, ac=3)(b, c, t, sp, lv)
    t.conditions['shielded'] = 5 * lv


def mirror_image(b, c, t, sp, lv):
    t.images = b.rng.randint(1, 4) + lv // 3
    b.log('%s is surrounded by %d images.' % (t.name, t.images))


def spiritual_hammer(b, c, t, sp, lv):
    b.swing(c, t, Attack(2, 1, 4, 1), melee=False, verb='strikes with a spiritual hammer')


def charm(b, c, t, sp, lv):
    if t.hd > 8 and sp.id in (10, 93):
        b.log('%s is too powerful to charm.' % t.name)
        return
    if _save(b, t):
        b.log('%s resists %s.' % (t.name, sp.name))
        return
    b.charm(t, c, 20)


def dispel(b, c, t, sp, lv):
    if t.effects or t.conditions or t.images:
        t.effects, t.images = [], 0
        for k in list(t.conditions):
            if k == 'charmed':
                b.uncharm(t)
        t.conditions = {}
        b.log('The magic on %s is dispelled.' % t.name)


def slay_living(b, c, t, sp, lv):
    if _save(b, t):
        dmg = roll(b.rng, 2, 8, 1)
        b.damage(t, dmg, '%s resists %s but takes %d.' % (t.name, sp.name, dmg))
    else:
        b.damage(t, t.hp + 10, '%s is slain by %s!' % (t.name, sp.name))


def cloudkill(b, c, t, sp, lv):
    if t.hd < 4 or (t.hd <= 6 and not _save(b, t, -4)):
        b.damage(t, t.hp + 10, '%s chokes to death in the cloud.' % t.name)
    else:
        dmg = roll(b.rng, 1, 10)
        b.damage(t, dmg, '%s takes %d from the cloud.' % (t.name, dmg))


def feeblemind(b, c, t, sp, lv):
    if _save(b, t, -4):
        b.log('%s resists %s.' % (t.name, sp.name))
    else:
        t.spells = []
        b.log("%s's mind is shattered: no more spells." % t.name)


def prayer(b, c, t, sp, lv):
    if t.side == c.side:
        modify('Prayer', lv, hit=1, save=1)(b, c, t, sp, lv)
    else:
        t.effects.append(['Prayer', lv, {'hit': -1, 'save': -1}])


def teleport(b, c, t, sp, lv):
    pass        # handled by Battle.cast (it needs the chosen square)


# party and area spells that only help
FRIENDLY_AREA = {1, 42, 48, 50, 52, 53, 61, 88, 92}

S = Spell
TABLE = [
    S(1, 'Bless', CLERIC, 1, 'party', effect=modify('Bless', 6, hit=1)),
    S(2, 'Curse', CLERIC, 1, 'foes', 12, 3, modify('Curse', 6, hit=-1), max_targets=99),
    S(3, 'Cure Light Wounds', CLERIC, 1, 'ally', 1, effect=heal(1, 8)),
    S(4, 'Cause Light Wounds', CLERIC, 1, 'enemy', 1, effect=damage(1, 8, save_half=None)),
    S(5, 'Detect Magic', CLERIC, 1, 'self', note='not used in combat'),
    S(6, 'Protection From Evil', CLERIC, 1, 'ally', 1, effect=modify('Protection', lambda lv: 3 * lv, ac=2, save=2)),
    S(7, 'Protection from Good', CLERIC, 1, 'ally', 1, effect=modify('Protection', lambda lv: 3 * lv, ac=2, save=2)),
    S(8, 'Resist Cold', CLERIC, 1, 'ally', 1, effect=modify('Resist Cold', 10, save=3)),
    S(9, 'Burning Hands', MAGE, 1, 'enemy', 1, effect=burning_hands),
    S(10, 'Charm Person', MAGE, 1, 'enemy', 12, effect=charm),
    S(11, 'Detect Magic', MAGE, 1, 'self', note='not used in combat'),
    S(12, 'Enlarge', MAGE, 1, 'ally', 3, effect=modify('Enlarge', lambda lv: 5 * lv, dmg=2)),
    S(13, 'Reduce', MAGE, 1, 'enemy', 3, effect=modify('Reduce', 10, dmg=-2)),
    S(14, 'Friends', MAGE, 1, 'self', note='not used in combat'),
    S(15, 'Magic Missile', MAGE, 1, 'enemy', 16, effect=magic_missile),
    S(16, 'Protection From Evil', MAGE, 1, 'ally', 1, effect=modify('Protection', lambda lv: 3 * lv, ac=2, save=2)),
    S(17, 'Protection From Good', MAGE, 1, 'ally', 1, effect=modify('Protection', lambda lv: 3 * lv, ac=2, save=2)),
    S(18, 'Read Magic', MAGE, 1, 'self', note='not used in combat'),
    S(19, 'Shield', MAGE, 1, 'self', effect=shield),
    S(20, 'Shocking Grasp', MAGE, 1, 'enemy', 1, effect=shocking_grasp),
    S(21, 'Sleep', MAGE, 1, 'area', 12, 1, condition('asleep', lambda lv: 5 * lv, save=False, hd_limit=4)),
    S(22, 'Find Traps', CLERIC, 2, 'self', note='not used in combat'),
    S(23, 'Hold Person', CLERIC, 2, 'foes', 12, 1, condition('held', lambda lv: 4 + lv), max_targets=3),
    S(24, 'Resist Fire', CLERIC, 2, 'ally', 1, effect=modify('Resist Fire', 10, save=3)),
    S(25, "Silence 15' Radius", CLERIC, 2, 'foes', 12, 2, condition('silenced', lambda lv: 2 * lv), max_targets=99),
    S(26, 'Slow Poison', CLERIC, 2, 'self', note='not used in combat'),
    S(27, 'Snake Charm', CLERIC, 2, 'self', note='not used in combat'),
    S(28, 'Spiritual Hammer', CLERIC, 2, 'enemy', 6, effect=spiritual_hammer),
    S(29, 'Detect Invisibility', MAGE, 2, 'self', note='not used in combat'),
    S(30, 'Invisibility', MAGE, 2, 'ally', 1, effect=condition('invisible', 30, save=False)),
    S(31, 'Knock', MAGE, 2, 'self', note='not used in combat'),
    S(32, 'Mirror Image', MAGE, 2, 'self', effect=mirror_image),
    S(33, 'Ray of Enfeeblement', MAGE, 2, 'enemy', 6, effect=modify('Enfeebled', 10, dmg=-2, hit=-1)),
    S(34, 'Stinking Cloud', MAGE, 2, 'area', 8, 1, condition('nauseated', 3)),
    S(35, 'Strength', MAGE, 2, 'ally', 1, effect=modify('Strength', 20, hit=1, dmg=1)),
    S(36, 'Animate Dead', CLERIC, 3, 'self', note='not used in combat'),
    S(37, 'Cure Blindness', CLERIC, 3, 'self', note='not used in combat'),
    S(38, 'Cause Blindness', CLERIC, 3, 'enemy', 1, effect=modify('Blinded', 10, hit=-4, ac=-4)),
    S(39, 'Cure Disease', CLERIC, 3, 'self', note='not used in combat'),
    S(40, 'Cause Disease', CLERIC, 3, 'enemy', 1, effect=modify('Diseased', 30, hit=-2, dmg=-1)),
    S(41, 'Dispel Magic', CLERIC, 3, 'area', 12, 1, dispel),
    S(42, 'Prayer', CLERIC, 3, 'party', effect=prayer),
    S(43, 'Remove Curse', CLERIC, 3, 'self', note='not used in combat'),
    S(44, 'Bestow Curse', CLERIC, 3, 'enemy', 1, effect=modify('Cursed', 20, hit=-4, save=-1)),
    S(45, 'Blink', MAGE, 3, 'self', effect=modify('Blink', lambda lv: lv, ac=4)),
    S(46, 'Dispel Magic', MAGE, 3, 'area', 12, 1, dispel),
    S(47, 'Fireball', MAGE, 3, 'area', 18, 2, level_damage(6, cap=10)),
    S(48, 'Haste', MAGE, 3, 'party', effect=condition('hasted', lambda lv: 3 + lv, save=False)),
    S(49, 'Hold Person', MAGE, 3, 'foes', 12, 1, condition('held', lambda lv: 2 * lv), max_targets=3),
    S(50, "Invisibility 10' Radius", MAGE, 3, 'party', effect=condition('invisible', 30, save=False)),
    S(51, 'Lightning Bolt', MAGE, 3, 'line', 0, 0, level_damage(6, cap=10), length=10),
    S(52, "Protection From Evil 10' Radius", MAGE, 3, 'party', effect=modify('Protection', 12, ac=2, save=2)),
    S(53, "Protection From Good 10' Radius", MAGE, 3, 'party', effect=modify('Protection', 12, ac=2, save=2)),
    S(54, 'Protection From Normal Missiles', MAGE, 3, 'ally', 1, effect=condition('missile_proof', 30, save=False)),
    S(55, 'Slow', MAGE, 3, 'foes', 12, 2, condition('slowed', lambda lv: 3 + lv), max_targets=99),
    S(56, 'Restoration', CLERIC, 7, 'self', note='not used in combat'),
    S(57, 'Cure Serious Wounds', CLERIC, 4, 'ally', 1, effect=heal(2, 8, 1)),
    S(58, 'Cause Serious Wounds', CLERIC, 4, 'enemy', 1, effect=damage(2, 8, 1, save_half=None)),
    S(59, 'Neutralize Poison', CLERIC, 4, 'self', note='not used in combat'),
    S(60, 'Poison', CLERIC, 4, 'enemy', 1, effect=slay_living),
    S(61, "Protection Evil 10' Radius", CLERIC, 4, 'party', effect=modify('Protection', 12, ac=2, save=2)),
    S(62, 'Sticks to Snakes', CLERIC, 4, 'self', note='not used in combat'),
    S(63, 'Cure Critical Wounds', CLERIC, 5, 'ally', 1, effect=heal(3, 8, 3)),
    S(64, 'Cause Critical Wounds', CLERIC, 5, 'enemy', 1, effect=damage(3, 8, 3, save_half=None)),
    S(65, 'Dispel Evil', CLERIC, 5, 'enemy', 1, effect=damage(4, 6, save_half=False)),
    S(66, 'Flame Strike', CLERIC, 5, 'area', 6, 0, damage(6, 8)),
    S(67, 'Raise Dead', CLERIC, 5, 'self', note='not used in combat'),
    S(68, 'Slay Living', CLERIC, 5, 'enemy', 6, effect=slay_living),
    S(69, 'Detect Magic', CLERIC, 1, 'self', note='not used in combat'),
    S(70, 'Entangle', CLERIC, 1, 'foes', 8, 1, condition('held', 2), max_targets=99),
    S(71, 'Faerie Fire', CLERIC, 1, 'foes', 8, 1, modify('Faerie Fire', 8, ac=-2), max_targets=99),
    S(72, 'Invisibility to Animals', CLERIC, 1, 'self', note='not used in combat'),
    S(73, 'Charm Monsters', MAGE, 4, 'enemy', 12, effect=charm),
    S(74, 'Confusion', MAGE, 4, 'foes', 12, 2, condition('confused', lambda lv: 2 + lv), max_targets=99),
    S(75, 'Dimension Door', MAGE, 4, 'square', 30, effect=teleport),
    S(76, 'Fear', MAGE, 4, 'cone', 0, 0, condition('afraid', lambda lv: lv), length=6),
    S(77, 'Fire Shield', MAGE, 4, 'self', effect=modify('Fire Shield', lambda lv: 2 + lv, ac=2)),
    S(78, 'Fumble', MAGE, 4, 'enemy', 12, effect=condition('held', 2)),
    S(79, 'Ice Storm', MAGE, 4, 'area', 12, 2, damage(3, 10, save_half=None)),
    S(80, 'Minor Globe Of Invulnerability', MAGE, 4, 'self', effect=condition('globe', lambda lv: lv, save=False)),
    S(81, 'Remove Curse', MAGE, 4, 'self', note='not used in combat'),
    S(82, 'Animate Dead', MAGE, 5, 'self', note='not used in combat'),
    S(83, 'Cloud Kill', MAGE, 5, 'area', 10, 2, cloudkill),
    S(84, 'Cone of Cold', MAGE, 5, 'cone', 0, 0, level_damage(4), length=6),
    S(85, 'Feeblemind', MAGE, 5, 'enemy', 12, effect=feeblemind),
    S(86, 'Hold Monsters', MAGE, 5, 'foes', 12, 1, condition('held', lambda lv: lv), max_targets=4),
    S(87, 'Bestow Curse', MAGE, 4, 'enemy', 1, effect=modify('Cursed', 20, hit=-4, save=-1)),
    S(88, "Protection From Evil 10' Radius", CLERIC, 4, 'party', effect=modify('Protection', 12, ac=2, save=2)),
    S(89, "Silence 15' radius", CLERIC, 2, 'foes', 12, 2, condition('silenced', lambda lv: 2 * lv), max_targets=99),
    S(90, 'Detect Magic', MAGE, 1, 'self', note='not used in combat'),
    S(91, 'Remove Curse', CLERIC, 3, 'self', note='not used in combat'),
    S(92, 'Bless', CLERIC, 1, 'party', effect=modify('Bless', 6, hit=1)),
    S(93, 'Charm Person', MAGE, 1, 'enemy', 12, effect=charm),
    S(94, 'Burning Hands', MAGE, 1, 'enemy', 1, effect=burning_hands),
]
SPELLS = {s.id: s for s in TABLE}


def spell(sid):
    return SPELLS.get(sid)


# ------------------------------------------------------------------ geometry
def area_cells(b, caster, sp, target):
    """Cells a spell aimed at `target` (a cell) would touch."""
    a = b.arena
    tx, ty = target
    if sp.shape in ('area', 'foes'):
        r = sp.radius
        return [(x, y) for x in range(tx - r, tx + r + 1) for y in range(ty - r, ty + r + 1)
                if a.inside(x, y) and math.hypot(x - tx, y - ty) <= r + 0.5]
    if sp.shape in ('line', 'cone'):
        cx, cy = caster.x, caster.y
        dx, dy = tx - cx, ty - cy
        if dx == 0 and dy == 0:
            return []
        n = max(abs(dx), abs(dy))
        ux, uy = dx / n, dy / n
        if sp.shape == 'line':
            out = []
            for k in range(1, sp.length + 1):
                p = (int(round(cx + ux * k)), int(round(cy + uy * k)))
                if not a.inside(*p) or a.opaque(*p):
                    break
                if p not in out:
                    out.append(p)
            return out
        ang = math.atan2(dy, dx)
        out = []
        for x in range(cx - sp.length, cx + sp.length + 1):
            for y in range(cy - sp.length, cy + sp.length + 1):
                if (x, y) == (cx, cy) or not a.inside(x, y) or a.opaque(x, y):
                    continue
                d = math.hypot(x - cx, y - cy)
                if d > sp.length + 0.5:
                    continue
                da = abs((math.atan2(y - cy, x - cx) - ang + math.pi) % (2 * math.pi) - math.pi)
                if da <= math.radians(30) + 0.5 / max(d, 1):
                    out.append((x, y))
        return out
    return [target]


def victims(b, caster, sp, target):
    """Combatants the spell would affect when aimed at `target` (cell or Combatant)."""
    if sp.shape == 'self':
        return [caster]
    friends = b.party if caster.side == PARTY else b.enemies
    foes = b.enemies if caster.side == PARTY else b.party
    if sp.shape == 'party':
        out = [f for f in friends if f.present]
        if sp.id == 42:                       # prayer also hinders every foe
            out += [f for f in foes if f.present]
        return out
    if sp.shape in ('ally', 'enemy'):
        return [target] if target is not None and not isinstance(target, tuple) else []
    if sp.shape == 'square':
        return [caster]
    cells = set(area_cells(b, caster, sp, target))
    hit = []
    for c in b.all:
        if c.present and c.status != FLED and any(p in cells for p in c.cells()):
            hit.append(c)
    if sp.shape == 'foes':
        hit = [c for c in hit if c in foes]
        hit.sort(key=lambda c: min(math.hypot(px - target[0], py - target[1]) for px, py in c.cells()))
        hit = hit[:sp.max_targets or 99]
    return hit


def caster_level(c, sp):
    return max(1, c.levels.get(sp.cls, 0) or c.hd)


def clear_path(b, c, cell):
    """True when no wall stands between c and the cell (creatures do not block spells)."""
    return any(not any(b.arena.opaque(*p) for p in b._line(x, y, *cell)[1:-1]) for x, y in c.cells())


def problem(b, c, sp, target=None):
    """Why c cannot cast sp now (None when it can)."""
    item = getattr(sp, 'item', None)
    if not sp.combat:
        return sp.note or 'not used in combat'
    if c.has('silenced') and (item is None or sp.slot is not None):
        return 'silenced'
    if c.attacked:
        return 'already acted'
    if item is None and sp.id not in c.spells:
        return 'not memorised'
    if not sp.needs_target or target is None:
        return None
    if sp.shape in ('ally', 'enemy'):
        t = target
        if t.side == c.side and sp.shape == 'enemy':
            return 'not a foe'
        if t.side != c.side and sp.shape == 'ally':
            return 'not a friend'
        if sp.range <= 1:
            if t is not c and not b.adjacent(c, t):
                return 'must touch the target'
        elif b.distance(c, t) > sp.range:
            return 'out of range (%d)' % sp.range
        elif t is not c and not any(clear_path(b, c, p) for p in t.cells()):
            return 'no line of sight'
        return None
    cell = target
    if sp.shape in ('area', 'foes', 'square'):
        if max(abs(cell[0] - c.x), abs(cell[1] - c.y)) > sp.range:
            return 'out of range (%d)' % sp.range
        if sp.shape == 'square':
            if not b.arena.passable(*cell) or b.occupant(*cell) is not None:
                return 'not an empty square'
            return None
        if b.arena.opaque(*cell):
            return 'into a wall'
        if not clear_path(b, c, cell):
            return 'no line of sight'
    return None


def cast(b, c, sp, target=None):
    """c casts sp (which must be castable); returns the combatants affected."""
    item = getattr(sp, 'item', None)
    c.attacked = True
    c.half_moves = 0
    if item is None:
        lv = caster_level(c, sp)
        c.spells.remove(sp.id)
        b.log('%s casts %s.' % (c.name, sp.name))
    else:
        lv = sp.cast_level or caster_level(c, sp.spell)
        b.log('%s uses %s.' % (c.name, sp.name))
        note = sp.use()
        if note:
            b.log(note)
    if sp.hostile:
        c.conditions.pop('invisible', None)
    if sp.shape == 'square':
        c.x, c.y = target
        b.log('%s steps through a door in space.' % c.name)
        return [c]
    hit = victims(b, c, sp, target)
    for t in hit:
        if t.has('globe') and sp.level <= 3 and t is not c and sp.hostile:
            b.log("%s's globe turns the spell aside." % t.name)
            continue
        sp.effect(b, c, t, sp, lv)
    b.check_end()
    return hit


# ------------------------------------------------------------------ AI
def _worth(t):
    return 1.0 + t.hd


def choose(b, c):
    """(spell, target) the AI would cast now, or None."""
    items = c.item_powers() if getattr(c, 'item_powers', None) else []
    if (not c.spells and not items) or c.attacked:
        return None
    friends = [f for f in (b.party if c.side == PARTY else b.enemies) if f.present]
    foes = [f for f in b.foes(c) if f.active]
    best = None
    seen = set()
    candidates = [] if c.has('silenced') else [SPELLS.get(sid) for sid in c.spells]
    candidates += items
    for sp in candidates:
        key = sp.name if getattr(sp, 'item', None) else sp and sp.id
        if sp is None or not sp.combat or key in seen or problem(b, c, sp) is not None:
            continue
        seen.add(key)
        options = []
        if getattr(sp, 'item', None) is not None and sp.shape == 'self':
            if sp.heals and c.hp < c.hp_max * 0.4:
                options.append((3.5 + (c.hp_max - c.hp) / 4.0, None))
            elif not sp.heals and foes and not c.has('hasted') and not c.has('invisible') \
                    and len(foes) >= 3:
                options.append((2.0, None))
        elif sp.shape == 'ally' and sp.id in (3, 57, 63):
            for f in friends:
                if f.hp < f.hp_max * 0.4 and problem(b, c, sp, f) is None:
                    options.append((3.0 + (f.hp_max - f.hp) / 4.0, f))
        elif sp.shape == 'party' and sp.id in (1, 42, 48, 92, 52, 53, 61, 88):
            fresh = [f for f in friends if not any(e[0] in ('Bless', 'Prayer', 'Protection')
                                                   for e in f.effects) and not f.has('hasted')]
            if len(fresh) >= 3 and foes:
                options.append((len(fresh) * (1.5 if sp.id == 48 else 0.6), None))
        elif sp.shape == 'enemy':
            for f in foes:
                if f.helpless or problem(b, c, sp, f) is not None:
                    continue
                if sp.id in (10, 73, 93):
                    options.append((2.0 + f.hd, f))
                elif sp.id == 15:
                    options.append((1.5 + (3.0 if f.hp <= 6 else 0), f))
                else:
                    options.append((1.0 + f.hd * 0.5, f))
        elif sp.shape in ('area', 'foes', 'line', 'cone'):
            for f in foes:
                for cell in f.cells():
                    if (sp.shape in ('area', 'foes') and problem(b, c, sp, cell) is not None):
                        continue
                    hit = victims(b, c, sp, cell)
                    score = 0.0
                    for h in hit:
                        if sp.id == 21 and h.hd > 4:
                            continue
                        if h.helpless and sp.id in (21, 23, 34, 49, 86, 70):
                            continue
                        score += _worth(h) * (1 if h in foes else -2.5)
                    if score >= 2.5:
                        options.append((score, cell))
        for score, target in options:
            score *= 1.0 + sp.level * 0.2
            if best is None or score > best[0]:
                best = (score, sp, target)
    if best is None:
        return None
    return best[1], best[2]
