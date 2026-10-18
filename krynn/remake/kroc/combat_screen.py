"""Overhead combat screen.

Keys on your turn:
    arrows / numpad / WASD + QEZC     move (QEZC and numpad 7 9 1 3 diagonally)
    moving into an enemy              attack it
    mouse: click a lit cell / enemy   walk there / attack it
    T                                 cycle the target shown in the panel
    RETURN or X                       attack the target (if next to you)
    F, or click a distant enemy       shoot the target (bow, sling, darts...)
    B                                 bandage a dying friend next to you
    M                                 cast a spell: pick it from the list (arrows + RETURN,
                                      or its number), then aim with the arrows or the
                                      mouse; the squares and creatures it will hit are
                                      shown before RETURN / click casts it. ESC cancels.
    G or SPACE                        end the turn (guard)
    U                                 let the computer play this character
    shift+U                           ... the whole party (U again to take back)
    L                                 leave: flee from the edge of the field
    V                                 zoom in/out
"""
import time

import pygame

from . import spells as SP
from .art import Art
from .combat import ENEMY, PARTY, OK, DYING, DEAD, FLED

DIRS = {
    pygame.K_UP: (0, -1), pygame.K_w: (0, -1), pygame.K_KP8: (0, -1),
    pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1), pygame.K_KP2: (0, 1),
    pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0), pygame.K_KP4: (-1, 0),
    pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0), pygame.K_KP6: (1, 0),
    pygame.K_q: (-1, -1), pygame.K_KP7: (-1, -1), pygame.K_e: (1, -1), pygame.K_KP9: (1, -1),
    pygame.K_z: (-1, 1), pygame.K_KP1: (-1, 1), pygame.K_c: (1, 1), pygame.K_KP3: (1, 1),
}

BG = (12, 12, 24)
PANEL = (24, 24, 48)
FRAME = (170, 120, 40)
TEXT = (235, 235, 235)
DIM = (150, 150, 170)
GOOD = (120, 220, 120)
BAD = (240, 100, 90)
HILITE = (255, 255, 85)
STEP_DELAY = 0.12
ATTACK_DELAY = 0.45
SHOT_TIME = 0.3           # an arrow's flight across the field


class CombatScreen:
    def __init__(self, app, battle):
        self.app = app
        self.b = battle
        self.font = app.font
        self.small = app.small
        self.tiny = getattr(app, "tiny", None) or pygame.font.Font(None, 24)
        self.art = Art(app.world, app.small)
        self.zoom = 1               # V: zoom in 2x around the active combatant
        self.ai = None
        self.next_ai = 0
        self.effects = []           # (until, kind, cell, text)
        self.shots = []             # (start px, end px, t0) arrows in flight
        self.flash = {}             # combatant -> until (attack pose)
        self.target = None
        self.done = False
        self.summary = None
        self.reach = {}
        self.auto_all = False
        self.hover = None
        self.casting = None         # {'list': [...], 'i': n} or {'spell': Spell, 'aim': cell}
        self.blast = None           # (until, cells, colour): a spell going off
        self.begin_turn()

    # --------------------------------------------------------------- turn flow
    @property
    def cur(self):
        return self.b.turn

    def begin_turn(self):
        c = self.b.next_turn()
        if c is None:
            self.finish()
            return
        self.casting = None
        if c.side == ENEMY or self.b.controlled_by_ai(c) or self.auto_all:
            self.ai = self.b.ai_turn(c)
            self.next_ai = time.time() + 0.25
        else:
            self.ai = None
            self.refresh()

    def refresh(self):
        c = self.cur
        self.reach = self.b.reachable(c) if c and not c.attacked else {}
        foes = self.b.foes(c) if c else []
        if self.target not in foes:
            self.target = min(foes, key=lambda f: self.b.distance(c, f)) if foes else None
        can_shoot = c is not None and self.b.shoot_target(c) is not None
        can_cast = c is not None and bool(self.castable(c))
        if c and c.side == PARTY and (c.attacked or (c.half_moves < 2 and not can_shoot and not can_cast
                                                     and not any(self.b.adjacent(c, f) for f in foes))):
            self.end_turn()

    def end_turn(self):
        if self.b.turn is not None:
            self.b.turn.guarding = not self.b.turn.attacked
        self.begin_turn()

    def finish(self):
        if self.summary is not None:
            return
        each = self.b.finish()
        r = self.b.result
        if r == 'won':
            self.summary = ['VICTORY!', 'Each survivor gains %d experience.' % each]
        elif r == 'fled':
            self.summary = ['The party escapes.']
        else:
            self.summary = ['The party has fallen...']
        self.summary.append('Press RETURN to continue.')

    def update(self):
        if self.summary is not None or not self.ai:
            return
        if time.time() < self.next_ai:
            return
        try:
            kind, what = next(self.ai)
        except StopIteration:
            self.ai = None
            self.end_turn()
            return
        if kind == 'attack':
            self.flash[self.cur] = time.time() + ATTACK_DELAY
            self.next_ai = time.time() + ATTACK_DELAY
        elif kind == 'cast':
            sp, target = what
            self.show_blast(self.cur, sp, target)
            self.next_ai = time.time() + 0.9
        elif kind == 'shoot':
            self.launch(self.cur, what)
            self.next_ai = time.time() + SHOT_TIME * self.cur.missile.shots + 0.2
        else:
            self.next_ai = time.time() + STEP_DELAY
        if self.b.check_end():
            self.ai = None
            self.finish()

    # --------------------------------------------------------------- input
    def key(self, ev):
        if self.summary is not None:
            if ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                self.done = True
            return
        if ev.key == pygame.K_v:
            self.zoom = 2 if self.zoom == 1 else 1
            return
        c = self.cur
        if ev.key == pygame.K_u:
            if ev.mod & pygame.KMOD_SHIFT:
                self.auto_all = not self.auto_all
                if not self.auto_all:
                    for p in self.b.party:
                        p.auto = False
            elif c is not None and c.side == PARTY:
                c.auto = not c.auto
            if c is not None and c.side == PARTY and (c.auto or self.auto_all) and self.ai is None:
                self.ai = self.b.ai_turn(c)
            return
        if self.ai is not None or c is None or c.side != PARTY:
            return
        if self.casting is not None:
            self.cast_key(ev)
            return
        if ev.key == pygame.K_m:
            self.open_spells()
        elif ev.key in DIRS:
            dx, dy = DIRS[ev.key]
            self.move_or_attack(dx, dy)
        elif ev.key == pygame.K_t:
            foes = sorted(self.b.foes(c), key=lambda f: self.b.distance(c, f))
            if foes:
                i = foes.index(self.target) if self.target in foes else -1
                self.target = foes[(i + 1) % len(foes)]
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) or ev.unicode.lower() == 'x':
            self.attack(self.target)
        elif ev.key == pygame.K_b:
            for p in self.b.party:
                if p.status == DYING and self.b.bandage(c, p):
                    self.refresh()
                    break
        elif ev.key in (pygame.K_g, pygame.K_SPACE):
            self.end_turn()
        elif ev.key == pygame.K_f:
            self.shoot(self.target)
        elif ev.key == pygame.K_l:
            if self.b.arena.edge(c.x, c.y):
                self.b.flee(c)
                self.end_turn()
            else:
                self.b.log('Move to the edge of the field to flee.')

    # --------------------------------------------------------------- spells
    def castable(self, c):
        """Distinct combat spells c still has, in the order memorised."""
        out = []
        for sid in c.spells:
            sp = SP.spell(sid)
            if sp is not None and sp.combat and sp not in out:
                out.append(sp)
        return out

    def open_spells(self):
        c = self.cur
        options = self.castable(c)
        if not options:
            self.b.log('%s has no combat spells left.' % c.name)
            return
        self.casting = {'list': options, 'i': 0}

    def cancel(self):
        if self.casting is not None:
            self.casting = None

    def cast_key(self, ev):
        st, c = self.casting, self.cur
        if ev.key == pygame.K_ESCAPE:
            # from aiming, step back to the list
            self.casting = {'list': self.castable(c), 'i': 0} if 'spell' in st else None
            return
        if 'list' in st:
            n = len(st['list'])
            if ev.key in (pygame.K_UP, pygame.K_KP8, pygame.K_w):
                st['i'] = (st['i'] - 1) % n
            elif ev.key in (pygame.K_DOWN, pygame.K_KP2, pygame.K_s):
                st['i'] = (st['i'] + 1) % n
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.pick_spell(st['list'][st['i']])
            elif ev.unicode.isdigit() and 0 < int(ev.unicode) <= n:
                self.pick_spell(st['list'][int(ev.unicode) - 1])
            return
        if ev.key in DIRS:
            dx, dy = DIRS[ev.key]
            x, y = st['aim'][0] + dx, st['aim'][1] + dy
            if self.b.arena.inside(x, y):
                st['aim'] = (x, y)
        elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) or ev.unicode.lower() == 'x':
            self.do_cast()

    def pick_spell(self, sp):
        c = self.cur
        why = SP.problem(self.b, c, sp)
        if why is not None:
            self.b.log('Cannot cast %s: %s.' % (sp.name, why))
            return
        if not sp.needs_target:
            self.casting = {'spell': sp, 'aim': (c.x, c.y)}
            self.do_cast()
            return
        if sp.shape == 'ally' or sp.shape == 'square' or self.target is None:
            aim = (c.x, c.y)
        else:
            aim = (self.target.x, self.target.y)
        self.casting = {'spell': sp, 'aim': aim}

    def aim_target(self):
        """What the spell being aimed is aimed at: a Combatant or a cell."""
        st = self.casting
        sp = st['spell']
        if sp.shape in ('ally', 'enemy'):
            o = self.b.occupant(*st['aim'])
            return o if o is not None and o.present else None
        if sp.shape == 'self' or sp.shape == 'party':
            return None
        return st['aim']

    def aim_problem(self):
        sp, t = self.casting['spell'], self.aim_target()
        if sp.needs_target and t is None:
            return 'no one there' if sp.shape in ('ally', 'enemy') else 'no target'
        if sp.shape in ('line', 'cone') and t == (self.cur.x, self.cur.y):
            return 'aim away from yourself'
        return SP.problem(self.b, self.cur, sp, t)

    def do_cast(self):
        c, sp = self.cur, self.casting['spell']
        why = self.aim_problem()
        if why is not None:
            self.b.log('Cannot cast %s: %s.' % (sp.name, why))
            return
        t = self.aim_target()
        self.casting = None
        self.show_blast(c, sp, t)
        SP.cast(self.b, c, sp, t)
        if self.b.check_end():
            self.finish()
            return
        self.refresh()

    def show_blast(self, c, sp, target):
        if sp.shape in ('self', 'party', 'ally', 'enemy', 'square'):
            cells = [p for v in SP.victims(self.b, c, sp, target) for p in v.cells()]
            if sp.shape == 'square':
                cells = [target]
        else:
            cells = SP.area_cells(self.b, c, sp, target)
        colour = (255, 120, 40, 110) if sp.hostile else (90, 170, 255, 100)
        self.blast = (time.time() + 0.8, cells, colour)

    def motion(self, pos):
        if self.casting is not None and 'list' in self.casting:
            i = self.list_row_at(pos)
            if i is not None:
                self.casting['i'] = i
        elif self.casting is not None and 'spell' in self.casting:
            cell = self.cell_at(pos)
            if cell is not None:
                self.casting['aim'] = cell

    def move_or_attack(self, dx, dy):
        c = self.cur
        o = None
        for cx, cy in c.cells(c.x + dx, c.y + dy):
            o = o or self.b.occupant(cx, cy, ignore=c)
        if o is not None and o.side != c.side and o.active:
            self.attack(o)
            return
        if self.b.step(c, dx, dy):
            if c.status == FLED:
                self.end_turn()
                return
            if not c.active:
                self.end_turn()
                return
            self.refresh()

    def launch(self, a, t):
        """Start the arrow animation from a to t."""
        cp = self.cell_px()
        ax, ay = self.to_px(a.x, a.y)
        tx, ty = self.to_px(t.x, t.y)
        now = time.time()
        for k in range(a.missile.shots):
            self.shots.append(((ax + a.w * cp // 2, ay + a.h * cp // 2),
                               (tx + t.w * cp // 2, ty + t.h * cp // 2), now + k * SHOT_TIME))

    def shoot(self, t):
        c = self.cur
        if t is None:
            return
        why = self.b.fire_problem(c, t)
        if why is not None:
            self.b.log('Cannot shoot: %s.' % why)
            return
        self.launch(c, t)
        self.b.fire(c, t)
        if self.b.check_end():
            self.finish()
            return
        self.refresh()

    def attack(self, t):
        c = self.cur
        if t is None or not self.b.adjacent(c, t) or c.attacked:
            if t is not None:
                self.b.log('%s is out of reach.' % t.name)
            return
        self.flash[c] = time.time() + ATTACK_DELAY
        self.b.attack(c, t)
        if self.b.check_end():
            self.finish()
            return
        self.refresh()

    def click(self, pos):
        if self.summary is not None:
            self.done = True
            return
        c = self.cur
        if c is None or c.side != PARTY or self.ai is not None:
            return
        if self.casting is not None:
            if 'list' in self.casting:
                i = self.list_row_at(pos)
                if i is not None:
                    self.pick_spell(self.casting['list'][i])
                return
            cell = self.cell_at(pos)
            if cell is not None:
                self.casting['aim'] = cell
                self.do_cast()
            return
        cell = self.cell_at(pos)
        if cell is None:
            return
        o = self.b.occupant(*cell)
        if o is not None and o.side != c.side and o.active:
            self.target = o
            if self.b.adjacent(c, o):
                self.attack(o)
            elif c.missile is not None:
                self.shoot(o)
            return
        path = self.b.path_to(c, cell)
        for p in path or []:
            if not self.b.step(c, p[0] - c.x, p[1] - c.y) or not c.active:
                break
        if c.active:
            self.refresh()
        else:
            self.end_turn()

    # --------------------------------------------------------------- geometry
    # layout on the 1920x1080 frame: the whole 29x21 field at 48 px a cell
    # (the original 24x24 icons and tiles at exactly 2x), panel on the right
    VIEW = pygame.Rect(24, 24, 29 * 48, 21 * 48)
    PANEL = pygame.Rect(VIEW.right + 24, 24, 1920 - VIEW.right - 48, 800)
    LOG = pygame.Rect(PANEL.x, PANEL.bottom + 16, PANEL.w, VIEW.bottom - PANEL.bottom - 16)

    def cell_px(self):
        return 48 * self.zoom

    def view_rect(self):
        return self.VIEW

    def camera(self):
        """Top-left cell shown, keeping the active combatant in view."""
        v, cp = self.view_rect(), self.cell_px()
        cols, rows = v.w // cp, v.h // cp
        a = self.b.arena
        focus = self.cur or self.b.party[0]
        cx = min(max(0, focus.x - cols // 2), max(0, a.w - cols))
        cy = min(max(0, focus.y - rows // 2), max(0, a.h - rows))
        return cx, cy

    def cell_at(self, pos):
        v, cp = self.view_rect(), self.cell_px()
        if not v.collidepoint(pos):
            return None
        cx, cy = self.camera()
        x, y = (pos[0] - v.x) // cp + cx, (pos[1] - v.y) // cp + cy
        return (x, y) if self.b.arena.inside(x, y) else None

    def to_px(self, x, y):
        v, cp = self.view_rect(), self.cell_px()
        cx, cy = self.camera()
        return v.x + (x - cx) * cp, v.y + (y - cy) * cp

    # --------------------------------------------------------------- drawing
    def draw(self, screen):
        screen.fill(BG)
        v, cp = self.view_rect(), self.cell_px()
        a = self.b.arena
        screen.set_clip(v)
        cx, cy = self.camera()
        cols, rows = v.w // cp + 1, v.h // cp + 1
        threat = self.b.threatened(PARTY) if self.cur and self.cur.side == PARTY else set()
        for y in range(cy, min(a.h, cy + rows)):
            for x in range(cx, min(a.w, cx + cols)):
                px, py = self.to_px(x, y)
                screen.blit(self.art.block(a.floor[y][x], cp), (px, py))
                bid = a.block[y][x]
                if bid is not None:
                    screen.blit(self.art.block(bid, cp, a.doors.get((x, y))), (px, py))
        # overlays for the active party member
        if self.cur and self.cur.side == PARTY and self.ai is None:
            ov = pygame.Surface((cp, cp), pygame.SRCALPHA)
            for (x, y), (cost, _) in self.reach.items():
                if (x, y) == (self.cur.x, self.cur.y):
                    continue
                ov.fill((80, 160, 255, 32) if (x, y) not in threat else (255, 120, 60, 64))
                screen.blit(ov, self.to_px(x, y))
        now = time.time()
        if self.casting is not None and 'spell' in self.casting:
            self.draw_aim(screen, cp)
        if self.blast is not None:
            until, cells, colour = self.blast
            if now < until:
                ov = pygame.Surface((cp, cp), pygame.SRCALPHA)
                ov.fill(colour)
                for p in cells:
                    screen.blit(ov, self.to_px(*p))
            else:
                self.blast = None
        # the line of a possible shot at the target
        cur, t = self.cur, self.target
        if cur is not None and cur.side == PARTY and self.ai is None and t is not None and t.active \
                and self.casting is None \
                and cur.missile is not None and self.b.fire_problem(cur, t) is None:
            a = self.to_px(cur.x, cur.y)
            b = self.to_px(t.x, t.y)
            a = (a[0] + cp // 2, a[1] + cp // 2)
            b = (b[0] + t.w * cp // 2, b[1] + t.h * cp // 2)
            n = max(1, int(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 // 14))
            for k in range(0, n, 2):
                p0 = (a[0] + (b[0] - a[0]) * k // n, a[1] + (b[1] - a[1]) * k // n)
                p1 = (a[0] + (b[0] - a[0]) * (k + 1) // n, a[1] + (b[1] - a[1]) * (k + 1) // n)
                pygame.draw.line(screen, (255, 230, 120), p0, p1, 2)
        # combatants
        now = time.time()
        for c in sorted(self.b.all, key=lambda c: (c.status == OK, c.y)):
            if c.status == FLED:
                continue
            px, py = self.to_px(c.x, c.y)
            w, h = c.w * cp, c.h * cp
            if c.status == DEAD:
                if c.side == PARTY:
                    pygame.draw.line(screen, BAD, (px + 4, py + 4), (px + cp - 4, py + cp - 4), 2)
                    pygame.draw.line(screen, BAD, (px + cp - 4, py + 4), (px + 4, py + cp - 4), 2)
                continue
            icon = self.icon(c, self.flash.get(c, 0) > now)
            if icon is not None:
                icon = pygame.transform.scale(icon, (w, h))
                if c.status == DYING:
                    icon = pygame.transform.rotate(icon, 90)
                screen.blit(icon, (px, py))
            else:
                pygame.draw.rect(screen, GOOD if c.side == PARTY else BAD, (px + 2, py + 2, w - 4, h - 4))
            # health bar
            frac = max(0, c.hp) / float(max(1, c.hp_max))
            pygame.draw.rect(screen, (0, 0, 0), (px + 3, py + h - 7, w - 6, 5))
            pygame.draw.rect(screen, GOOD if frac > 0.5 else (HILITE if frac > 0.25 else BAD),
                             (px + 3, py + h - 7, int((w - 6) * frac), 5))
            if c is self.cur:
                pulse = 3 + 2 * (int(now * 4) % 2)
                pygame.draw.rect(screen, HILITE, (px, py, w, h), pulse)
            elif c is self.target and self.cur and self.cur.side == PARTY and self.casting is None:
                pygame.draw.rect(screen, BAD, (px, py, w, h), 3)
            self.draw_marks(screen, c, px, py, w)
        self.draw_shots(screen, now)
        screen.set_clip(None)
        pygame.draw.rect(screen, FRAME, v.inflate(12, 12), 3)
        self.draw_panel(screen)
        self.draw_log(screen)
        if self.summary is not None:
            self.draw_summary(screen)

    MARKS = (('asleep', 'Zz', (150, 190, 255)), ('held', 'HELD', (255, 210, 90)),
             ('nauseated', 'SICK', (150, 220, 90)), ('charmed', 'CHARM', (255, 140, 220)),
             ('confused', '???', (255, 160, 60)), ('afraid', 'FEAR', (255, 255, 255)),
             ('slowed', 'SLOW', (170, 170, 170)), ('hasted', 'FAST', (120, 255, 200)),
             ('silenced', 'MUTE', (200, 200, 200)), ('invisible', 'INVIS', (180, 220, 255)))

    def draw_marks(self, screen, c, px, py, w):
        """Small tags over a combatant for the spells affecting it."""
        tags = [(t, col) for k, t, col in self.MARKS if c.has(k)]
        if c.images:
            tags.append(('x%d' % c.images, (200, 200, 255)))
        if c.effects:
            good = any(sum(m.values()) > 0 for _, _, m in c.effects)
            tags.append(('+' if good else '-', GOOD if good else BAD))
        x = px + 2
        for text, col in tags[:3]:
            img = self.tiny.render(text, True, col)
            bg = pygame.Surface((img.get_width() + 4, img.get_height()), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 170))
            screen.blit(bg, (x, py + 1))
            screen.blit(img, (x + 2, py + 1))
            x += img.get_width() + 6

    def draw_aim(self, screen, cp):
        """The squares the spell would cover and who it would hit."""
        c, sp = self.cur, self.casting['spell']
        t = self.aim_target()
        bad = self.aim_problem()
        if sp.shape in ('area', 'foes', 'line', 'cone'):
            cells = SP.area_cells(self.b, c, sp, self.casting['aim'])
            ov = pygame.Surface((cp, cp), pygame.SRCALPHA)
            ov.fill((120, 120, 120, 70) if bad else
                    ((255, 120, 40, 80) if sp.hostile else (90, 170, 255, 80)))
            for p in cells:
                screen.blit(ov, self.to_px(*p))
        if not bad:
            for v in SP.victims(self.b, c, sp, t):
                px, py = self.to_px(v.x, v.y)
                friend = v.side == c.side
                col = (HILITE if sp.hostile else GOOD) if friend else BAD
                pygame.draw.rect(screen, col, (px - 2, py - 2, v.w * cp + 4, v.h * cp + 4), 4)
        px, py = self.to_px(*self.casting['aim'])
        pygame.draw.rect(screen, (120, 120, 120) if bad else (255, 255, 255), (px, py, cp, cp), 2)

    def draw_shots(self, screen, now):
        live = []
        for start, end, t0 in self.shots:
            f = (now - t0) / SHOT_TIME
            if f > 1:
                continue
            live.append((start, end, t0))
            if f < 0:
                continue
            x = start[0] + (end[0] - start[0]) * f
            y = start[1] + (end[1] - start[1]) * f
            dx, dy = end[0] - start[0], end[1] - start[1]
            ln = max(1.0, (dx * dx + dy * dy) ** 0.5)
            tail = (x - dx / ln * 22, y - dy / ln * 22)
            pygame.draw.line(screen, (240, 240, 220), tail, (x, y), 3)
            pygame.draw.circle(screen, (255, 255, 255), (int(x), int(y)), 3)
        self.shots = live

    def icon(self, c, attacking):
        kind = c.icon[0]
        if kind == 'party':
            return self.art.party_icon(c.icon[1])
        return self.art.monster_icon(c.icon[1], attacking, c.icon[2])

    def draw_panel(self, screen):
        r = self.PANEL
        pygame.draw.rect(screen, PANEL, r)
        pygame.draw.rect(screen, FRAME, r, 3)
        x, y = r.x + 20, r.y + 16
        c = self.cur
        put = lambda text, col, dx=0, font=None: screen.blit((font or self.small).render(text, True, col), (x + dx, y))
        put('ROUND %d' % self.b.round, DIM)
        y += 44
        for p in self.b.party:
            col = TEXT if p.status == OK else (BAD if p.status in (DYING, DEAD) else DIM)
            if p is c:
                col = HILITE
            st = {OK: '%d/%d' % (p.hp, p.hp_max), DYING: 'DYING', DEAD: 'DEAD', FLED: 'FLED'}[p.status]
            put(p.name[:15], col)
            t = self.small.render('%s  AC %d' % (st, p.ac), True, col if p is c else DIM)
            screen.blit(t, (r.right - 20 - t.get_width(), y))
            y += 38
        y += 16
        if c is not None:
            who = c.name if c.side == PARTY else c.name + ' (enemy)'
            put('TURN: ' + who[:20], HILITE)
            y += 36
            if c.side == PARTY:
                put('Moves left %d' % (c.half_moves // 2), DIM)
                y += 36
                if c.missile is not None:
                    m = c.missile
                    put('%s, %d shot%s' % (m.name, m.shots, 's' if m.shots > 1 else ''), DIM)
                    y += 34
                    left = m.left()
                    put('range %d%s' % (m.range, '' if left is None else ', %d %s' % (left, m.ammo_name)), DIM)
                    y += 36
                spells = [x for x in c.spells if SP.spell(x) and SP.spell(x).combat]
                if spells:
                    put('M: cast a spell (%d left)' % len(spells), GOOD if not c.attacked else DIM)
                    y += 36
        if self.casting is not None and c is not None:
            self.draw_spell_panel(screen, r, y)
            return
        t = self.target
        if t is not None and t.active and c is not None and c.side == PARTY:
            y += 8
            put('TARGET: ' + t.name[:18], BAD)
            y += 34
            put('HP %d/%d   AC %d' % (t.hp, t.hp_max, t.ac), DIM)
            y += 34
            pct = int(round(self.b.to_hit(c, t) * 100))
            put('Hit %d%%   damage %s' % (pct, ' '.join(a.text() for a in c.attacks)), DIM)
            y += 34
            put('in reach' if self.b.adjacent(c, t) else '%d squares away' % self.b.distance(c, t), DIM)
            if c.missile is not None and not self.b.adjacent(c, t):
                y += 34
                why = self.b.fire_problem(c, t)
                if why is None:
                    put('F: shoot %dx %s, hit %d%%' % (c.missile.shots, c.missile.attack.text(),
                                                     int(round(self.b.missile_to_hit(c, t) * 100))), GOOD)
                else:
                    put('cannot shoot: ' + why, DIM)

    LIST_ROW = 36

    def list_row_at(self, pos):
        st = self.casting
        if not st or 'list' not in st or 'top' not in st:
            return None
        x, y = pos
        if not self.PANEL.collidepoint(pos) or y < st['top']:
            return None
        i = (y - st['top']) // self.LIST_ROW
        return i if 0 <= i < len(st['list']) else None

    def draw_spell_panel(self, screen, r, y):
        c, st = self.cur, self.casting
        x = r.x + 20
        y += 8
        if 'list' in st:
            screen.blit(self.small.render('CAST WHICH SPELL?', True, HILITE), (x, y))
            y += 40
            st['top'] = y
            for i, sp in enumerate(st['list']):
                n = c.spells.count(sp.id)
                why = SP.problem(self.b, c, sp)
                col = HILITE if i == st['i'] else (TEXT if why is None else DIM)
                if i == st['i']:
                    pygame.draw.rect(screen, (50, 50, 90), (r.x + 8, y - 2, r.w - 16, self.LIST_ROW))
                label = '%d %s' % (i + 1, sp.name) if i < 9 else '  ' + sp.name
                screen.blit(self.small.render(label[:24], True, col), (x, y))
                t = self.small.render('x%d  L%d' % (n, sp.level), True, DIM)
                screen.blit(t, (r.right - 20 - t.get_width(), y))
                y += self.LIST_ROW
                if y > r.bottom - 80:
                    break
            sp = st['list'][st['i']]
            y = r.bottom - 74
            screen.blit(self.small.render(self.describe(sp)[:34], True, DIM), (x, y))
            screen.blit(self.small.render('RETURN choose   ESC back', True, DIM), (x, y + 34))
            return
        sp = st['spell']
        screen.blit(self.small.render(sp.name.upper()[:26], True, HILITE), (x, y))
        y += 38
        screen.blit(self.small.render(self.describe(sp)[:34], True, DIM), (x, y))
        y += 44
        why = self.aim_problem()
        if why is not None:
            screen.blit(self.small.render('Cannot: ' + why, True, BAD), (x, y))
        else:
            hit = SP.victims(self.b, c, sp, self.aim_target())
            foes = [v for v in hit if v.side != c.side]
            friends = [v for v in hit if v.side == c.side]
            if foes:
                screen.blit(self.small.render('Foes: %d' % len(foes), True, BAD), (x, y))
                y += 34
                for v in foes[:3 if friends else 5]:
                    screen.blit(self.small.render('  ' + v.name[:22], True, TEXT), (x, y))
                    y += 32
            if friends:
                if sp.hostile:
                    text, col = 'WARNING: hits %d friend%s' % (len(friends), 's' * (len(friends) > 1)), HILITE
                else:
                    text, col = 'Friends: %d' % len(friends), GOOD
                screen.blit(self.small.render(text, True, col), (x, y))
                y += 34
                for v in friends[:3]:
                    screen.blit(self.small.render('  ' + v.name[:22], True, TEXT), (x, y))
                    y += 32
            if not hit:
                screen.blit(self.small.render('No one is in the area.', True, DIM), (x, y))
        screen.blit(self.small.render('aim: arrows or mouse', True, DIM), (x, r.bottom - 74))
        screen.blit(self.small.render('RETURN/click cast  ESC back', True, DIM), (x, r.bottom - 40))

    @staticmethod
    def describe(sp):
        shape = {'self': 'on yourself', 'party': 'on the whole party', 'ally': 'on a friend',
                 'enemy': 'on one foe', 'foes': 'on foes in an area',
                 'area': 'everyone in the area', 'line': 'a bolt', 'cone': 'a cone',
                 'square': 'to an empty square'}[sp.shape]
        rng = '' if sp.shape in ('self', 'party') else (
            ', touch' if sp.range <= 1 and sp.shape in ('ally', 'enemy') else
            (', length %d' % sp.length if sp.shape in ('line', 'cone') else ', range %d' % sp.range))
        return shape + rng

    def draw_log(self, screen):
        r = self.LOG
        pygame.draw.rect(screen, PANEL, r)
        pygame.draw.rect(screen, FRAME, r, 3)
        n = (r.h - 24) // 34
        rows = []
        for ln in self.b.log_lines[-n:]:
            words, line = ln.split(' '), ''
            for wd in words:
                t = (line + ' ' + wd).strip()
                if self.small.size(t)[0] > r.w - 32 and line:
                    rows.append(line)
                    line = '  ' + wd
                else:
                    line = t if not line.startswith('  ') else line + ' ' + wd
            rows.append(line)
        y = r.y + 12
        for ln in rows[-n:]:
            screen.blit(self.small.render(ln, True, TEXT), (r.x + 16, y))
            y += 34
        help_ = ('arrows/QEZC move   bump or click: attack   F shoot   M magic   T target   '
                 'B bandage   SPACE end turn   U auto   L flee   V zoom')
        screen.blit(self.small.render(help_, True, DIM), (self.VIEW.x, self.VIEW.bottom + 14))

    def draw_summary(self, screen):
        r = pygame.Rect(0, 0, 900, 80 + 56 * len(self.summary))
        r.center = self.VIEW.center
        pygame.draw.rect(screen, (40, 0, 0) if self.b.result == 'lost' else (0, 30, 10), r)
        pygame.draw.rect(screen, FRAME, r, 4)
        y = r.y + 40
        for i, ln in enumerate(self.summary):
            screen.blit(self.font.render(ln, True, HILITE if i == 0 else TEXT), (r.x + 48, y))
            y += 56
