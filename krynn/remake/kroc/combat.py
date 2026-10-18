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
"""
import heapq
import random

from cok.geo import DX, DY

PARTY, ENEMY = 'party', 'enemy'
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

    @property
    def active(self):
        return self.status == OK

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
        self.order = sorted((c for c in self.all if c.active), key=lambda c: (c.init, c.side == ENEMY))
        self.log('-- Round %d --' % self.round)

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
            if c.active:
                c.half_moves = 2 * c.move
                c.attacks_left = sum(a.half for a in c.attacks)
                c.attacked = False
                c.guarding = False
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
            if c.active and e.active and not self.adjacent(e, c) and not e.aoo_used:
                e.aoo_used = True
                self.log('%s gets a free attack.' % e.name)
                self.attack(e, c, free=True)
        return True

    def flee(self, c):
        c.status = FLED
        self.log('%s flees the battle.' % c.name)
        return True

    # --- attacks --------------------------------------------------------------------
    def to_hit(self, a, d):
        """Chance (0..1) that a hits d with one swing."""
        need = a.thac0 - d.ac
        need = max(2, min(20, need))
        return (21 - need) / 20.0

    def attack(self, a, d, free=False):
        """One attack round of a against d (all of a's attacks, or one when free)."""
        if not free:
            a.attacked = True
            a.half_moves = 0
        swings = []
        for atk in a.attacks:
            n = max(1, atk.half // 2) if not free else 1
            swings += [atk] * n
            if free:
                break
        if not free:
            a.attacks_left = 0
        for atk in swings:
            if not d.present or d.status == DYING and d.side == ENEMY:
                break
            r = self.rng.randint(1, 20)
            need = a.thac0 - d.ac
            if r == 20 or (r != 1 and r >= need):
                dmg = max(1, roll(self.rng, atk.dice, atk.size, atk.bonus))
                self.damage(d, dmg, '%s hits %s for %d.' % (a.name, d.name, dmg))
            else:
                self.log('%s misses %s.' % (a.name, d.name))
        self.check_end()

    def damage(self, d, n, text):
        d.hp -= n
        self.log(text)
        if d.hp <= 0 and d.status == OK:
            if d.side == ENEMY or d.hp <= -10:
                d.status = DEAD
                self.log('%s is killed.' % d.name)
            else:
                d.status = DYING
                self.log('%s goes down!' % d.name)

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
        """Generator of ('move', (x, y)) / ('attack', target) as the AI acts."""
        foes = self.foes(c)
        if not foes:
            return
        if any(self.adjacent(c, f) for f in foes):
            target = min((f for f in foes if self.adjacent(c, f)), key=lambda f: f.hp)
            yield ('attack', target)
            self.attack(c, target)
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
        foes = [f for f in self.foes(c) if self.adjacent(c, f)]
        if foes and c.active:
            target = min(foes, key=lambda f: f.hp)
            yield ('attack', target)
            self.attack(c, target)

    def distance_cells(self, c, cell, f):
        return min(max(abs(cx - fx), abs(cy - fy))
                   for cx, cy in c.cells(*cell) for fx, fy in f.cells())

    # --- end of fight --------------------------------------------------------------
    def finish(self):
        """Apply the outcome to the party; returns experience per survivor."""
        each = 0
        if self.result == 'won':
            total = sum(e.xp for e in self.enemies if e.status == DEAD)
            alive = [c for c in self.party if c.status in (OK, DYING)]
            each = total // len(alive) if alive else 0
            for c in self.party:
                if c.status == DYING:
                    c.hp = 0                     # stabilised after the fight
        for c in self.party:
            if c.ref is not None:
                c.ref.hp = max(c.hp, -10)
                c.ref.dead = c.status == DEAD
                if self.result == 'won' and c.status in (OK, DYING):
                    c.ref.experience += each
        return each
