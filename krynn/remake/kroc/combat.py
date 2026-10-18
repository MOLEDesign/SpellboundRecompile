"""Tactical combat on an overhead grid (rules only, no drawing).

The original draws its battlefield in a fake isometric projection, but its
rules are plain square-grid rules. This module keeps those rules and lays
the battlefield out straight from above:

* every 3D map square becomes 3x3 floor cells, and the walls between squares
  become a 1-cell line of wall blocks (doors are passable gaps when open);
* outdoors the field is open ground with trees, bushes, logs and rocks.

Every cell that is not plain floor carries a block id (see blocks.py) so
its graphics can be replaced later.

AD&D rules as the Gold Box uses them: d6 initiative each round, a d20 roll
against THAC0 - AC to hit, damage dice per attack, half-moves for movement
(orthogonal 2, diagonal 3; budget = 2 x movement), attacks of opportunity
when leaving an enemy's reach, and dying characters losing 1 HP a round
until bandaged or dead at -10.

Missiles (bows, crossbows, slings, darts, javelins, hoopaks): a combatant
with a missile weapon and ammunition may shoot instead of fighting in melee
at a foe in range and in line of sight (walls and other creatures block),
but not while an enemy stands next to it. Each shot uses ammunition; dex,
not strength, adjusts the roll, and beyond half range there is -2.
"""
import heapq
import random

from cok.geo import DX, DY

PARTY, ENEMY = 'party', 'enemy'
CONDITION_WORDS = {'fleeing': 'fleeing', 'asleep': 'asleep', 'held': 'held', 'nauseated': 'helpless with nausea',
                   'slowed': 'slowed', 'hasted': 'hasted', 'confused': 'confused',
                   'afraid': 'afraid', 'silenced': 'silenced', 'charmed': 'charmed',
                   'invisible': 'invisible'}
OK, DYING, DEAD, FLED = 'ok', 'dying', 'dead', 'fled'

# 8 neighbour steps: (dx, dy, half-move cost)
STEPS = [(0, -1, 2), (1, 0, 2), (0, 1, 2), (-1, 0, 2),
         (1, -1, 3), (1, 1, 3), (-1, 1, 3), (-1, -1, 3)]

SQUARE = 4          # cells per map square including one wall line
SPAN_X, SPAN_Y = 3, 2   # map squares shown either side of the party


def roll(rng, n, size, bonus=0):
    return sum(rng.randint(1, size) for _ in range(n)) + bonus if size else n + bonus


class Attack:
    __slots__ = ('half', 'dice', 'size', 'bonus')

    def __init__(self, half, dice, size, bonus=0):
        self.half, self.dice, self.size, self.bonus = half, dice, size, bonus

    def text(self):
        b = '%+d' % self.bonus if self.bonus else ''
        return '%dd%d%s' % (self.dice, self.size, b) if self.size else '%d' % max(1, self.dice + self.bonus)


class Missile:
    """A ranged weapon in someone's hands."""

    def __init__(self, name, dice, size, bonus, shots, range_, thac0, ammo=None, ammo_name='',
                 consumed=None):
        self.name = name
        self.attack = Attack(2, dice, size, bonus)
        self.shots = max(1, shots)
        self.range = range_
        self.thac0 = thac0              # to-hit for missiles (dexterity, no strength)
        self.ammo = ammo                # cok.items.Item whose quantity is used up, or None
        self.ammo_name = ammo_name
        self.consumed = consumed        # 'ammo' (arrows...) / 'thrown' (darts...) / None
        self.fired = 0

    def left(self):
        return None if self.ammo is None else self.ammo.quantity

    def text(self):
        left = self.left()
        amm = '' if left is None else ', %d %s' % (left, self.ammo_name or 'left')
        return '%s x%d, range %d%s' % (self.name, self.shots, self.range, amm)


class Combatant:
    def __init__(self, name, side, hp, hp_max, ac, thac0, attacks, move, icon,
                 size=(1, 1), xp=0, ref=None):
        self.name = name
        self.side = side
        self.hp, self.hp_max = hp, hp_max
        self.ac, self.thac0 = ac, thac0
        self.attacks = attacks          # list of Attack
        self.move = move
        self.icon = icon                # ('party', index) / ('monster', id)
        self.w, self.h = size
        self.xp = xp
        self.ref = ref                  # world Character for the party
        self.x = self.y = 0
        self.status = OK if hp > 0 else DYING
        self.auto = side == ENEMY
        self.init = 0
        self.half_moves = 0
        self.attacks_left = 0
        self.attacked = False
        self.guarding = False
        self.aoo_used = False
        self.missile = None             # Missile, if it can shoot
        # magic
        self.spells = []                # memorised spell ids still available
        self.levels = {'C': 0, 'M': 0}  # caster levels: cleric, magic-user
        self.hd = 1                     # hit dice / level (sleep, hold...)
        self.save_spell = 16            # d20 roll needed to save against spells
        self.effects = []               # [name, rounds, {hit/ac/dmg/save: n}]
        self.conditions = {}            # name -> rounds left: asleep, held, slowed ...
        self.images = 0                 # mirror images left
        self.cast_this_turn = False
        # morale (monsters): d100 roll needed to keep fighting when things go badly
        self.morale = None              # None: never breaks (the party, the mindless)
        self.morale_checked = set()     # triggers already rolled for

    @property
    def active(self):
        return self.status == OK

    # --- magic state -------------------------------------------------------------
    def mod(self, key):
        return sum(m.get(key, 0) for _, _, m in self.effects)

    @property
    def eff_ac(self):
        return self.ac - self.mod('ac')

    @property
    def helpless(self):
        return any(k in self.conditions for k in ('asleep', 'held', 'nauseated'))

    @property
    def can_act(self):
        return self.active and not self.helpless

    def has(self, cond):
        return cond in self.conditions
    @property
    def present(self):
        return self.status in (OK, DYING)

    def cells(self, x=None, y=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        return [(x + i, y + j) for i in range(self.w) for j in range(self.h)]

    def __repr__(self):
        return '<%s %s %d/%d @%d,%d>' % (self.side, self.name, self.hp, self.hp_max, self.x, self.y)


# ---------------------------------------------------------------- arena
class Arena:
    """Grid of cells: floor[y][x] is a floor block id, block[y][x] a blocking
    block id or None. Cells outside the grid are off the field (fleeing)."""

    def __init__(self, w, h, floor):
        self.w, self.h = w, h
        self.floor = [[floor] * w for _ in range(h)]
        self.block = [[None] * w for _ in range(h)]
        self.doors = {}                  # (x, y) -> door bits (1 open, 2/3 locked)

    def inside(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def passable(self, x, y):
        if not self.inside(x, y):
            return False
        if self.block[y][x] is None:
            return True
        return self.doors.get((x, y)) == 1

    def opaque(self, x, y):
        return self.inside(x, y) and self.block[y][x] is not None and self.doors.get((x, y)) != 1

    def edge(self, x, y):
        return x in (0, self.w - 1) or y in (0, self.h - 1)


def dungeon_arena(geo, px, py, wall_id, door_id, floor_id):
    """Map squares around (px, py), straight from above.

    wall_id(t) / door_id(t) give the block id for wall type t.
    Returns (arena, origin) where origin maps square (sx, sy) to cells.
    """
    nx, ny = 2 * SPAN_X + 1, 2 * SPAN_Y + 1
    a = Arena(nx * SQUARE + 1, ny * SQUARE + 1, floor_id)
    x0, y0 = px - SPAN_X, py - SPAN_Y

    def wall_between(sx, sy, d):
        """Wall type on side d of map square (sx, sy), seen from either side."""
        if not (0 <= sx < 16 and 0 <= sy < 16):
            return 0, 1
        t = geo.wall(sx, sy, d)
        door = geo.door(sx, sy, d)
        ox, oy = sx + DX[d], sy + DY[d]
        if t == 0 and 0 <= ox < 16 and 0 <= oy < 16:
            t = geo.wall(ox, oy, (d + 4) % 8)
            door = geo.door(ox, oy, (d + 4) % 8)
        return t, door

    def put_line(cells, t, door):
        """A wall line between two squares; a door is the middle cell only."""
        mid = cells[len(cells) // 2]
        for c in cells:
            if door != 0 and c == mid:
                a.block[c[1]][c[0]] = door_id(t)
                a.doors[c] = door
            else:
                a.block[c[1]][c[0]] = wall_id(t)

    for j in range(ny):
        for i in range(nx):
            sx, sy = x0 + i, y0 + j
            cx, cy = i * SQUARE, j * SQUARE
            if not (0 <= sx < 16 and 0 <= sy < 16):
                for yy in range(cy, cy + SQUARE + 1):
                    for xx in range(cx, cx + SQUARE + 1):
                        a.block[yy][xx] = 'EDGE'
                continue
            lines = [(0, [(cx + k, cy) for k in range(1, SQUARE)]),
                     (6, [(cx, cy + k) for k in range(1, SQUARE)])]
            if j == ny - 1:      # south/east lines only on the last row/column
                lines.append((4, [(cx + k, cy + SQUARE) for k in range(1, SQUARE)]))
            if i == nx - 1:
                lines.append((2, [(cx + SQUARE, cy + k) for k in range(1, SQUARE)]))
            for d, cells in lines:
                t, door = wall_between(sx, sy, d)
                if t:
                    put_line(cells, t, door)
    # corner posts: solid where any wall line meets
    for yy in range(0, a.h, SQUARE):
        for xx in range(0, a.w, SQUARE):
            if a.block[yy][xx] is not None:
                continue
            around = [(xx + 1, yy), (xx - 1, yy), (xx, yy + 1), (xx, yy - 1)]
            ids = [a.block[c[1]][c[0]] for c in around if a.inside(*c) and a.block[c[1]][c[0]]]
            walls = [b for b in ids if b != 'EDGE']
            if walls:
                a.block[yy][xx] = walls[0]      # a post between door cells stays solid
            elif ids:
                a.block[yy][xx] = 'EDGE'
    return a, (x0, y0)


def open_arena(rng, w=29, h=21, floor_ids=('F-WILD-12',), scatter=()):
    """Outdoor field: floor with scattered obstacles (scatter: block ids)."""
    a = Arena(w, h, floor_ids[0])
    for y in range(h):
        for x in range(w):
            a.floor[y][x] = rng.choice(floor_ids)
    if scatter:
        for _ in range(w * h // 14):
            x, y = rng.randrange(w), rng.randrange(h)
            if 9 <= x <= 19 and 6 <= y <= 14:
                continue            # keep the middle clear for the fight
            a.block[y][x] = rng.choice(scatter)
    return a


# ---------------------------------------------------------------- battle
class Battle:
    def __init__(self, arena, party, enemies, rng=None, log=None):
        self.arena = arena
        self.rng = rng or random.Random()
        self.party = party
        self.enemies = enemies
        self.all = party + enemies
        self.round = 0
        self.order = []
        self.turn = None
        self.log_lines = []
        self.logf = log
        self.result = None              # 'won', 'lost', 'fled'
        self.start_count = {PARTY: len(party), ENEMY: len(enemies)}

    # --- bookkeeping ---------------------------------------------------------
    def log(self, text):
        self.log_lines.append(text)
        if self.logf:
            self.logf(text)

    def occupant(self, x, y, ignore=None):
        for c in self.all:
            if c is not ignore and c.present and c.status != FLED and (x, y) in c.cells():
                return c
        return None

    def fits(self, c, x, y):
        for cx, cy in c.cells(x, y):
            if not self.arena.passable(cx, cy):
                return False
            o = self.occupant(cx, cy, ignore=c)
            if o is not None:
                return False
        return True

    def adjacent(self, a, b):
        """True when a can reach b in melee (any cells 8-adjacent)."""
        for ax, ay in a.cells():
            for bx, by in b.cells():
                if max(abs(ax - bx), abs(ay - by)) == 1:
                    return True
        return False

    def distance(self, a, b):
        return min(max(abs(ax - bx), abs(ay - by)) for ax, ay in a.cells() for bx, by in b.cells())

    def foes(self, c):
        return [o for o in (self.enemies if c.side == PARTY else self.party) if o.active]

    # --- placement --------------------------------------------------------------
    def place(self, start, facing):
        """Party around `start` (cell), enemies ahead in direction `facing`."""
        taken = set()

        def spots(origin, prefer):
            seen, q, out = {origin}, [origin], []
            while q:
                p = q.pop(0)
                out.append(p)
                for dx, dy, _ in STEPS[:4]:
                    n = (p[0] + dx, p[1] + dy)
                    if n not in seen and self.arena.passable(*n):
                        seen.add(n)
                        q.append(n)
            out.sort(key=prefer)
            return out

        # party: nearest free cells, preferring those behind the leader
        order = spots(start, lambda p: abs(p[0] - start[0]) + abs(p[1] - start[1])
                      + 0.5 * ((p[0] - start[0]) * DX[facing] + (p[1] - start[1]) * DY[facing] > 0))
        for c in self.party:
            for p in order:
                if p not in taken and self.fits(c, *p) and not any(q in taken for q in c.cells(*p)):
                    c.x, c.y = p
                    taken.update(c.cells())
                    break
        # enemies: about 6-9 cells ahead, or as far as the room allows
        ahead = (start[0] + DX[facing] * 7, start[1] + DY[facing] * 7)
        target = min(order, key=lambda p: abs(p[0] - ahead[0]) + abs(p[1] - ahead[1]))
        eorder = spots(target, lambda p: abs(p[0] - target[0]) + abs(p[1] - target[1]))
        for c in self.enemies:
            for p in eorder:
                cells = c.cells(*p)
                if self.fits(c, *p) and not any(q in taken for q in cells) and \
                        abs(p[0] - start[0]) + abs(p[1] - start[1]) >= 3:
                    c.x, c.y = p
                    taken.update(cells)
                    break
            else:
                c.status = FLED         # no room: it never joins the fight

    # --- rounds ----------------------------------------------------------------------
    def start_round(self):
        self.round += 1
        for c in self.all:
            if c.status == DYING and c.side == PARTY and not getattr(c, 'bandaged', False):
                c.hp -= 1
                if c.hp <= -10:
                    c.status = DEAD
                    self.log('%s dies.' % c.name)
            c.aoo_used = False
            c.init = self.rng.randint(1, 6)
            self.tick_magic(c)
        self.check_morale()
        self.order = sorted((c for c in self.all if c.active), key=lambda c: (c.init, c.side == ENEMY))
        self.log('-- Round %d --' % self.round)

    def tick_magic(self, c):
        """Count down spell effects at the start of a round."""
        for e in list(c.effects):
            e[1] -= 1
            if e[1] <= 0:
                c.effects.remove(e)
        for k in list(c.conditions):
            c.conditions[k] -= 1
            if c.conditions[k] <= 0:
                del c.conditions[k]
                if k == 'charmed':
                    self.uncharm(c)
                    continue
                if c.active:
                    self.log('%s is no longer %s.' % (c.name, CONDITION_WORDS.get(k, k)))

    def next_turn(self):
        """Advance to the next combatant that can act; None when the fight is over."""
        if self.check_end():
            self.turn = None
            return None
        while True:
            if not self.order:
                self.start_round()
                if not self.order:
                    return None
            c = self.order.pop(0)
            if c.active and not c.helpless:
                c.half_moves = 2 * c.move
                if c.has('hasted'):
                    c.half_moves *= 2
                if c.has('slowed'):
                    c.half_moves //= 2
                c.attacks_left = sum(a.half for a in c.attacks)
                c.attacked = False
                c.guarding = False
                c.cast_this_turn = False
                self.turn = c
                return c

    def check_end(self):
        if self.result:
            return True
        if not any(c.active for c in self.enemies):
            self.result = 'won'
        elif not any(c.active for c in self.party):
            self.result = 'fled' if any(c.status == FLED for c in self.party) else 'lost'
        return self.result is not None

    # --- movement ------------------------------------------------------------------
    def reachable(self, c):
        """{cell: (cost, previous cell)} the combatant can still move to."""
        start = (c.x, c.y)
        best = {start: (0, None)}
        heap = [(0, start)]
        while heap:
            cost, p = heapq.heappop(heap)
            if cost > best[p][0]:
                continue
            for dx, dy, step in STEPS:
                n = (p[0] + dx, p[1] + dy)
                nc = cost + step
                if nc > c.half_moves or not self.fits(c, *n):
                    continue
                if dx and dy and not (self.fits(c, p[0] + dx, p[1]) or self.fits(c, p[0], p[1] + dy)):
                    continue        # no squeezing diagonally between two walls
                if n not in best or nc < best[n][0]:
                    best[n] = (nc, p)
                    heapq.heappush(heap, (nc, n))
        return best

    def path_to(self, c, cell):
        r = self.reachable(c)
        if cell not in r:
            return None
        path = []
        while cell != (c.x, c.y):
            path.append(cell)
            cell = r[cell][1]
        return path[::-1]

    def threatened(self, side):
        """Cells next to active combatants of the other side."""
        out = set()
        for e in (self.enemies if side == PARTY else self.party):
            if e.active:
                for ex, ey in e.cells():
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            out.add((ex + dx, ey + dy))
        return out

    def step(self, c, dx, dy):
        """Move one cell; returns False if not allowed. May trigger free attacks."""
        if c.attacked:
            return False
        cost = 3 if dx and dy else 2
        nx, ny = c.x + dx, c.y + dy
        if not self.arena.inside(nx, ny) and self.arena.edge(c.x, c.y):
            if c.half_moves >= cost:
                return self.flee(c)
            return False
        if cost > c.half_moves or not self.fits(c, nx, ny):
            return False
        if dx and dy and not (self.fits(c, c.x + dx, c.y) or self.fits(c, c.x, c.y + dy)):
            return False
        # leaving an enemy's reach gives it a free attack
        before = [e for e in self.foes(c) if self.adjacent(e, c)]
        c.x, c.y = nx, ny
        c.half_moves -= cost
        for e in before:
            if c.active and e.can_act and not self.adjacent(e, c) and not e.aoo_used:
                e.aoo_used = True
                self.log('%s gets a free attack.' % e.name)
                self.attack(e, c, free=True)
        return True

    # --- morale ---------------------------------------------------------------------
    def check_morale(self):
        """Monsters roll to keep fighting the first time each bad thing happens:
        half their side down, or themselves below a third of their hit points.
        A monster that runs gives no experience."""
        side = self.enemies
        start = self.start_count[ENEMY]
        if start < 2:
            return          # a lone monster (often the villain of the piece) fights to the end
        lost = sum(1 for c in side if c.status in (DEAD, FLED))
        broke = []
        for c in side:
            if c.morale is None or not c.active or c.has('fleeing') or hasattr(c, 'home'):
                continue
            triggers = []
            if lost * 2 >= start:
                triggers.append('half')
            if c.hp * 3 < c.hp_max:
                triggers.append('hurt')
            for t in triggers:
                if t in c.morale_checked:
                    continue
                c.morale_checked.add(t)
                if self.rng.randint(1, 100) > c.morale:
                    c.conditions['fleeing'] = 999
                    broke.append(c)
                    break
        if len(broke) > 1:
            self.log('%d %ss break and run!' % (len(broke), broke[0].name) if
                     len({b.name for b in broke}) == 1 else 'The enemy breaks and runs!')
        elif broke:
            self.log('%s breaks and runs!' % broke[0].name)

    def exit_distance(self, c):
        """{cell: steps to the edge of the field} over open ground (creatures ignored)."""
        a = self.arena
        dist, q = {}, []
        for y in range(a.h):
            for x in range(a.w):
                if a.edge(x, y) and a.passable(x, y):
                    dist[(x, y)] = 0
                    q.append((x, y))
        i = 0
        while i < len(q):
            p = q[i]
            i += 1
            for dx, dy, _ in STEPS:
                n = (p[0] + dx, p[1] + dy)
                if n not in dist and a.inside(*n) and a.passable(*n):
                    dist[n] = dist[p] + 1
                    q.append(n)
        return dist

    def escape(self, c):
        """A fleeing monster heads for the edge of the field and leaves it."""
        dist = self.exit_distance(c)
        far = 10 ** 6
        here = min(dist.get(p, far) for p in c.cells())
        if here >= far:
            # nowhere to run: it fights on, cornered
            c.conditions.pop('fleeing', None)
            c.morale = None
            self.log('%s is cornered and fights on!' % c.name)
            return
        r = self.reachable(c)
        foes = self.foes(c)
        cell = min(r, key=lambda p: (min(dist.get(q, far) for q in c.cells(*p)),
                                     -min((self.distance_cells(c, p, f) for f in foes), default=0),
                                     r[p][0]))
        for p in self.path_to(c, cell) or []:
            if not self.step(c, p[0] - c.x, p[1] - c.y):
                break
            yield ('move', p)
            if not c.active:
                return
        if c.active and any(self.arena.edge(*p) for p in c.cells()):
            c.status = FLED
            self.log('%s escapes.' % c.name)
            self.check_end()
        c.attacked = True

    # --- charm ------------------------------------------------------------------------
    def charm(self, t, caster, rounds):
        """t fights for the caster's side until the charm ends or is dispelled."""
        if t.side == caster.side:
            return
        if not hasattr(t, 'home'):
            t.home, t.home_auto = t.side, t.auto
        (self.party if t.side == PARTY else self.enemies).remove(t)
        (self.party if caster.side == PARTY else self.enemies).append(t)
        t.side = caster.side
        t.auto = True
        t.conditions['charmed'] = rounds
        self.log('%s is charmed by %s!' % (t.name, caster.name))
        self.check_end()

    def uncharm(self, t):
        t.conditions.pop('charmed', None)
        home = getattr(t, 'home', None)
        if home is None or home == t.side:
            return
        (self.party if t.side == PARTY else self.enemies).remove(t)
        (self.party if home == PARTY else self.enemies).append(t)
        t.side, t.auto = home, t.home_auto
        del t.home, t.home_auto
        if t.present:
            self.log('%s comes to their senses.' % t.name)

    def controlled_by_ai(self, c):
        """Monsters, party members on auto, and anyone confused or terrified."""
        return c.auto or c.has('confused') or c.has('afraid')

    def flee(self, c):
        c.status = FLED
        self.log('%s flees the battle.' % c.name)
        return True

    # --- attacks --------------------------------------------------------------------
    def need(self, a, d, thac0=None, penalty=0):
        """d20 roll a needs to hit d (spell effects included)."""
        thac0 = a.thac0 if thac0 is None else thac0
        n = thac0 - a.mod('hit') - d.eff_ac + penalty
        if d.has('invisible'):
            n += 4
        return max(2, min(20, n))

    def to_hit(self, a, d):
        """Chance (0..1) that a hits d with one swing."""
        if d.helpless:
            return 1.0
        return (21 - self.need(a, d)) / 20.0

    def swing(self, a, d, atk, thac0=None, penalty=0, melee=True, verb='hits'):
        """One blow or shot of a at d; returns True on a hit."""
        if melee and d.helpless and d.side != a.side:
            # the Gold Box coup de grace: a helpless victim in melee dies
            self.damage(d, d.hp + (10 if d.side == PARTY else 0),
                        '%s slays the helpless %s.' % (a.name, d.name))
            return True
        extra_hit, extra_dmg, mult = self.slaying(a, d)
        r = self.rng.randint(1, 20)
        if d.helpless or r == 20 or (r != 1 and r >= self.need(a, d, thac0, penalty - extra_hit)):
            if d.images > 0 and self.rng.randrange(d.images + 1) > 0:
                d.images -= 1
                self.log('%s strikes one of %s\'s images.' % (a.name, d.name))
                return False
            dmg = max(1, (roll(self.rng, atk.dice, atk.size, atk.bonus) + a.mod('dmg') + extra_dmg) * mult)
            self.damage(d, dmg, '%s %s %s for %d.' % (a.name, verb, d.name, dmg))
            return True
        self.log(('%s misses %s.' if melee else '%s shoots at %s and misses.') % (a.name, d.name))
        return False

    @staticmethod
    def slaying(a, d):
        """(to hit, damage, multiplier) a's weapon gains against d's kind."""
        s = getattr(a, 'slayer', None)
        if s and any(w in d.name.upper() for w in s[0]):
            return s[1], s[2], s[3]
        return 0, 0, 1

    def attack(self, a, d, free=False):
        """One attack round of a against d (all of a's attacks, or one when free)."""
        if not free:
            a.attacked = True
            a.half_moves = 0
            a.conditions.pop('invisible', None)
        swings = []
        for atk in a.attacks:
            n = max(1, atk.half // 2) if not free else 1
            if not free and a.has('hasted'):
                n *= 2
            if not free and a.has('slowed'):
                n = max(1, n // 2)
            swings += [atk] * n
            if free:
                break
        if not free:
            a.attacks_left = 0
        for atk in swings:
            if not d.present or d.status == DYING and d.side == ENEMY:
                break
            self.swing(a, d, atk)
        self.check_end()

    def damage(self, d, n, text):
        d.hp -= n
        self.log(text)
        if d.conditions.pop('asleep', None) and d.hp > 0:
            self.log('%s wakes up!' % d.name)
        if d.hp <= 0 and d.status == OK:
            if d.side == ENEMY or d.hp <= -10:
                d.status = DEAD
                self.log('%s is killed.' % d.name)
            else:
                d.status = DYING
                self.log('%s goes down!' % d.name)

    # --- missiles ---------------------------------------------------------------
    @staticmethod
    def _line(x0, y0, x1, y1):
        """Cells crossed going from cell centre to cell centre (both ends included)."""
        n = max(abs(x1 - x0), abs(y1 - y0))
        out = []
        for i in range(n + 1):
            t = i / n if n else 0
            p = (int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t)))
            if not out or out[-1] != p:
                out.append(p)
        return out

    def line_of_sight(self, a, d):
        """True when a clear line runs from one of a's cells to one of d's."""
        for ax, ay in a.cells():
            for dx, dy in d.cells():
                ok = True
                for p in self._line(ax, ay, dx, dy)[1:-1]:
                    if self.arena.opaque(*p):
                        ok = False
                        break
                    o = self.occupant(*p)
                    if o is not None and o is not a and o is not d and o.status == OK:
                        ok = False
                        break
                if ok:
                    return True
        return False

    def fire_problem(self, a, d):
        """Why a cannot shoot at d now (None when it can)."""
        m = a.missile
        if m is None:
            return 'no missile weapon'
        if a.attacked:
            return 'already attacked'
        if m.left() is not None and m.left() <= 0:
            return 'out of ' + (m.ammo_name or 'ammunition')
        if any(self.adjacent(a, f) for f in self.foes(a) if f.can_act):
            return 'an enemy is next to you'
        if self.distance(a, d) > m.range:
            return 'out of range (%d)' % m.range
        if not self.line_of_sight(a, d):
            return 'no clear shot'
        return None

    def missile_to_hit(self, a, d):
        m = a.missile
        if d.helpless:
            return 1.0
        need = self.need(a, d, m.thac0, 2 if self.distance(a, d) > m.range // 2 else 0)
        return (21 - need) / 20.0

    def fire(self, a, d):
        """a shoots its missile weapon at d (all its shots this round)."""
        m = a.missile
        a.attacked = True
        a.half_moves = 0
        a.conditions.pop('invisible', None)
        long_range = self.distance(a, d) > m.range // 2
        shots = m.shots * (2 if a.has('hasted') else 1)
        if a.has('slowed'):
            shots = max(1, shots // 2)
        for _ in range(shots):
            if not d.present or (d.status == DYING and d.side == ENEMY):
                break
            if m.left() is not None:
                if m.left() <= 0:
                    self.log('%s is out of %s.' % (a.name, m.ammo_name or 'ammunition'))
                    break
                m.ammo.quantity -= 1
            m.fired += 1
            if d.has('missile_proof'):
                self.log('The missile cannot harm %s.' % d.name)
                continue
            self.swing(a, d, m.attack, m.thac0, 2 if long_range else 0, melee=False, verb='shoots')
        self.check_end()

    def shoot_target(self, c):
        """Best foe c can shoot right now (weakest first), or None."""
        ok = [f for f in self.foes(c) if self.fire_problem(c, f) is None]
        return min(ok, key=lambda f: (f.hp, self.distance(c, f))) if ok else None

    def bandage(self, a, d):
        if d.status == DYING and self.adjacent(a, d):
            d.bandaged = True
            a.attacked = True
            a.half_moves = 0
            self.log('%s bandages %s.' % (a.name, d.name))
            return True
        return False

    # --- simple AI (monsters, and party members on auto) -------------------------------
    def ai_turn(self, c):
        """Generator of ('move', (x, y)) / ('attack', target) / ('shoot', target) /
        ('cast', (spell, target)) as the AI acts."""
        from . import spells
        if c.has('fleeing'):
            yield from self.escape(c)
            if c.has('fleeing') or not c.active:
                return
        if c.has('afraid'):
            yield from self.run_away(c)
            return
        if c.has('confused'):
            roll_ = self.rng.randint(1, 10)
            if roll_ <= 2:
                yield from self.wander(c)
                return
            if roll_ <= 5:
                self.log('%s stands confused.' % c.name)
                c.attacked = True
                return
        foes = self.foes(c)
        if not foes:
            return
        pick = spells.choose(self, c)
        if pick is not None:
            yield ('cast', pick)
            spells.cast(self, c, *pick)
            return
        if any(self.adjacent(c, f) for f in foes):
            target = min((f for f in foes if self.adjacent(c, f)), key=lambda f: f.hp)
            yield ('attack', target)
            self.attack(c, target)
            return
        t = self.shoot_target(c)
        if t is not None:
            yield ('shoot', t)
            self.fire(c, t)
            return
        r = self.reachable(c)
        # head for the cell next to the closest foe
        goals = []
        for f in foes:
            for cell in r:
                if self.distance_cells(c, cell, f) == 1:
                    goals.append((r[cell][0], cell, f))
        if goals:
            _, cell, f = min(goals, key=lambda g: (g[0], g[1]))
        else:
            f = min(foes, key=lambda f: self.distance(c, f))
            cell = min(r, key=lambda p: (self.distance_cells(c, p, f), r[p][0]))
        for p in self.path_to(c, cell) or []:
            if not self.step(c, p[0] - c.x, p[1] - c.y):
                break
            yield ('move', p)
            if not c.active:
                return
            if c.missile is not None and self.shoot_target(c) is not None:
                break               # close enough to shoot: stop and fire
        foes = [f for f in self.foes(c) if self.adjacent(c, f)]
        if foes and c.active:
            target = min(foes, key=lambda f: f.hp)
            yield ('attack', target)
            self.attack(c, target)
        elif c.active and not c.attacked:
            t = self.shoot_target(c)
            if t is not None:
                yield ('shoot', t)
                self.fire(c, t)

    def run_away(self, c):
        """Move as far from the nearest foes as this turn allows."""
        foes = self.foes(c)
        r = self.reachable(c)
        if foes and r:
            cell = max(r, key=lambda p: (min(self.distance_cells(c, p, f) for f in foes), -r[p][0]))
            for p in self.path_to(c, cell) or []:
                if not self.step(c, p[0] - c.x, p[1] - c.y):
                    break
                yield ('move', p)
                if not c.active:
                    return
        c.attacked = True
        if c.active:
            self.log('%s cowers in fear.' % c.name)

    def wander(self, c):
        self.log('%s wanders about in confusion.' % c.name)
        for _ in range(self.rng.randint(1, 3)):
            dx, dy, _cost = self.rng.choice(STEPS)
            if not self.step(c, dx, dy):
                break
            yield ('move', (c.x, c.y))
            if not c.active:
                return
        c.attacked = True

    def distance_cells(self, c, cell, f):
        return min(max(abs(cx - fx), abs(cy - fy))
                   for cx, cy in c.cells(*cell) for fx, fy in f.cells())

    # --- end of fight --------------------------------------------------------------
    def finish(self):
        """Apply the outcome to the party; returns experience per survivor."""
        for c in list(self.all):
            self.uncharm(c)
        each = 0
        if self.result == 'won':
            total = sum(e.xp for e in self.enemies if e.status == DEAD)
            alive = [c for c in self.party if c.status in (OK, DYING)]
            each = total // len(alive) if alive else 0
            for c in self.party:
                if c.status == DYING:
                    c.hp = 0                     # stabilised after the fight
        for c in self.party:
            m = c.missile
            if m is not None and m.ammo is not None and self.result == 'won' and m.fired:
                # after a victory the party gathers what it can: all thrown
                # weapons, half of the arrows and quarrels
                m.ammo.quantity += m.fired if m.consumed == 'thrown' else m.fired // 2
            if c.ref is not None:
                c.ref.hp = max(c.hp, -10)
                c.ref.dead = c.status == DEAD
                if self.result == 'won' and c.status in (OK, DYING):
                    c.ref.gain(each)
        return each
