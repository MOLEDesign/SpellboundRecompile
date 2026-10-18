"""pygame front end: draws the original graphics, drives the ECL VM."""
import os
import time

import pygame

from cok import gfx, view3d
from cok.geo import DX, DY

from . import encounter
from .combat_screen import CombatScreen
from .world import World, OVERLAND_X, OVERLAND_Y

SCALE = 3
W, H = 320, 200
FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'PixelifySans.ttf')

BG = (16, 16, 40)
FRAME = (170, 120, 40)
TEXT = (255, 255, 255)
HILITE = (255, 255, 85)
DIM = (150, 150, 170)

VIEW = pygame.Rect(8, 8, 88, 88)
BIG = pygame.Rect(8, 8, 304, 120)
ROSTER = pygame.Rect(104, 8, 208, 88)

KEYS = {
    pygame.K_UP: 'forward', pygame.K_w: 'forward', pygame.K_KP8: 'forward',
    pygame.K_DOWN: 'back', pygame.K_s: 'back', pygame.K_KP2: 'back',
    pygame.K_LEFT: 'left', pygame.K_a: 'left', pygame.K_KP4: 'left',
    pygame.K_RIGHT: 'right', pygame.K_d: 'right', pygame.K_KP6: 'right',
    pygame.K_l: 'search', pygame.K_f: 'search',
}


def indexed_surface(pixels, width, height, palette):
    """Colour indices -> 8-bit pygame Surface."""
    s = pygame.Surface((width, height), depth=8)
    s.set_palette(palette)
    pitch = s.get_pitch()
    if pitch == width:
        s.get_buffer().write(bytes(pixels))
    else:
        buf = s.get_buffer()
        for y in range(height):
            buf.write(bytes(pixels[y * width:(y + 1) * width]), y * pitch)
    return s


def surface_from(pic, frame=0, transparent=None):
    """Picture frame -> pygame Surface (8-bit with palette)."""
    s = indexed_surface(pic.frames[frame], pic.width, pic.height, pic.rgb_palette())
    if transparent is not None:
        s.set_colorkey(transparent)
    return s


class App:
    def __init__(self, source=None, scale=SCALE, fullscreen=False):
        pygame.init()
        pygame.display.set_caption('Champions of Krynn - remake')
        flags = pygame.FULLSCREEN | pygame.SCALED if fullscreen else 0
        self.scale = scale
        self.screen = pygame.display.set_mode((W * scale, H * scale), flags)
        self.canvas = pygame.Surface((W, H))
        self.font = pygame.font.Font(FONT, 8 * scale)
        self.small = pygame.font.Font(FONT, 6 * scale)
        self.clock = pygame.time.Clock()
        self.notes = []
        self.world = World(log=self.log, files=None if source is None else None)
        if source:
            from .world import Files
            self.world = World(files=Files(source), log=self.log)
        self.renderer = view3d.Renderer()
        self.lines = []             # finished text lines
        self.para = ''              # text being accumulated
        self.menu = None            # (items, horizontal)
        self.sel = 0
        self.picture = None         # (Picture, kind)
        self.sprite = None          # (Picture, distance)
        self.combat = None          # CombatScreen while fighting
        self.wait_until = 0
        self.show_map = False
        self.visited = set()
        self.cache = {}
        self.gen = self.world.start()
        self.answer = None
        self.running = True
        self.status = ''

    # ------------------------------------------------------------------ util
    def log(self, text):
        self.notes.append(text)
        self.add_text(text, False)

    def add_text(self, text, clear):
        if clear:
            self.lines, self.para = [], ''
        for part in text.split('\n'):
            self.para += part
            if part is not text.split('\n')[-1]:
                self.flush()

    def flush(self):
        if self.para.strip():
            self.lines.append(self.para.strip())
        self.para = ''

    def pic(self, pid):
        if pid not in self.cache:
            self.cache[pid] = self.world.files.picture(pid)
        return self.cache[pid]

    # ------------------------------------------------------------------ VM pump
    def pump(self):
        """Run the script until it needs the player."""
        while self.gen and not self.menu and not self.combat and time.time() >= self.wait_until:
            try:
                req = self.gen.send(self.answer)
            except StopIteration:
                self.gen = None
                self.flush()
                break
            self.answer = None
            k = req[0]
            if k == 'print':
                self.add_text(req[1], req[2])
            elif k == 'menu':
                self.flush()
                self.menu, self.sel = (req[1], req[2]), 0
            elif k == 'picture':
                pid = req[1]
                if pid == 0xFF:
                    self.picture = None
                    self.sprite = None
                else:
                    p = self.pic(pid)
                    if p is not None:
                        self.picture = (p, 'big' if p.width > 88 else 'pic', time.time())
            elif k == 'sprite':
                sp = self.world.files.sprite(req[1])
                if sp is not None:
                    self.sprite = (sp, min(req[2], len(sp.frames) - 1))
            elif k == 'clearbox':
                self.lines, self.para = [], ''
            elif k == 'delay':
                self.wait_until = time.time() + 0.6
            elif k == 'combat':
                self.flush()
                self.combat = CombatScreen(self, encounter.build(self.world, req[1], self.world.vm.rng))
            elif k == 'program':
                if req[1] == 9:
                    self.world.rest()
                    self.add_text('The party rests and recovers.', False)
                    self.flush()
            elif k == 'treasure':
                self.add_text('You find treasure.', False)
                self.flush()
            elif k == 'note':
                print('[ecl]', req[1])
            elif k == 'block':
                self.picture = None
                self.sprite = None
            elif k == 'redraw':
                pass
        if self.world.in_dungeon and self.world.geo:
            self.visited.add((self.world.geo_id, self.world.x, self.world.y))

    def act(self, action):
        if self.gen or self.menu or self.combat:
            return
        self.picture = None if self.picture and self.world.in_dungeon else self.picture
        self.sprite = None
        self.gen = self.world.step(action)
        self.pump()

    def choose(self, n):
        self.menu = None
        self.answer = n
        self.lines, self.para = ([], '') if self.lines and len(self.lines) > 6 else (self.lines, self.para)
        self.pump()

    # ------------------------------------------------------------------ input
    def key(self, ev):
        if ev.key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
            return
        if self.combat is not None:
            self.combat.key(ev)
            self.end_combat_if_done()
            return
        if ev.key == pygame.K_ESCAPE and not self.menu:
            self.running = False
            return
        if self.menu:
            items, horiz = self.menu
            back, fwd = (pygame.K_LEFT, pygame.K_RIGHT) if horiz else (pygame.K_UP, pygame.K_DOWN)
            if ev.key in (back, pygame.K_a if horiz else pygame.K_w):
                self.sel = (self.sel - 1) % len(items)
            elif ev.key in (fwd, pygame.K_d if horiz else pygame.K_s):
                self.sel = (self.sel + 1) % len(items)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                self.choose(self.sel)
            elif ev.unicode and ev.unicode.isalnum():
                c = ev.unicode.upper()
                for n, it in enumerate(items):
                    if it[:1].upper() == c:
                        self.choose(n)
                        break
            return
        if ev.key == pygame.K_m:
            self.show_map = not self.show_map
            return
        if ev.key in KEYS:
            self.act(KEYS[ev.key])

    def end_combat_if_done(self):
        if self.combat is not None and self.combat.done:
            result = self.combat.b.result
            self.combat = None
            if result == 'lost':
                # the party is dead: back to the start, as the original does
                self.world = World(files=self.world.files, log=self.log)
                self.lines, self.para, self.picture, self.sprite = [], '', None, None
                self.add_text('The party has perished. A new band gathers at the Inn...', True)
                self.flush()
                self.gen = self.world.start()
                self.answer = None
            else:
                self.answer = result == 'won'
            self.pump()

    def click(self, pos):
        if self.menu:
            for n, r in enumerate(self.menu_rects):
                if r.collidepoint(pos):
                    self.choose(n)
                    return
        elif self.combat is not None:
            self.combat.click(pos)
            self.end_combat_if_done()

    # ------------------------------------------------------------------ drawing
    def draw(self):
        if self.combat is not None:
            self.combat.draw(self.screen)
            pygame.display.flip()
            return
        c = self.canvas
        c.fill(BG)
        w = self.world
        big = self.picture and self.picture[1] == 'big'
        overland = not w.in_dungeon and not self.picture and self.pic(0x79) is not None
        if big or overland:
            p = self.picture[0] if big else self.pic(0x79)
            c.blit(surface_from(p, self._frame(p)), BIG.topleft)
            pygame.draw.rect(c, FRAME, BIG.inflate(4, 4), 1)
            if overland:
                x, y = w.vm.get(OVERLAND_X), w.vm.get(OVERLAND_Y)
                if int(time.time() * 3) % 2:
                    pygame.draw.rect(c, (255, 255, 255), (BIG.x + x * 8, BIG.y + y * 8, 8, 8), 1)
            text_top = 132
        else:
            self._draw_view(c)
            pygame.draw.rect(c, FRAME, VIEW.inflate(4, 4), 1)
            pygame.draw.rect(c, FRAME, ROSTER.inflate(4, 4), 1)
            text_top = 104
        pygame.draw.rect(c, FRAME, (6, text_top - 2, 308, 196 - text_top), 1)
        pygame.transform.scale(c, self.screen.get_size(), self.screen)
        if not (big or overland):
            self._draw_roster()
        self._draw_text(text_top)
        pygame.display.flip()

    def _frame(self, p):
        if len(p.frames) == 1 or not self.picture:
            return 0
        t = time.time() - self.picture[2]
        n = len(p.frames) - 1
        return 1 + int(t * 4) % n if t > 0.5 else 0

    def _draw_view(self, c):
        w = self.world
        if self.picture and self.picture[1] == 'pic':
            p = self.picture[0]
            c.blit(surface_from(p, self._frame(p)), VIEW.topleft)
        elif self.show_map and w.geo:
            self._draw_map(c)
        elif w.geo and w.slots:
            buf = self.renderer.render(w.geo, w.x, w.y, w.facing, w.slots)
            s = indexed_surface(buf, 88, 88, gfx.EGA * 2)
            c.blit(s, VIEW.topleft)
        else:
            c.fill((0, 0, 0), VIEW)
        if self.sprite:
            sp, dist = self.sprite
            key = gfx.transparent_index(sp)
            c.blit(surface_from(sp, dist, key), VIEW.topleft)

    def _draw_map(self, c):
        w = self.world
        c.fill((0, 0, 0), VIEW)
        cell = 5
        ox, oy = VIEW.x + 4, VIEW.y + 4
        for y in range(16):
            for x in range(16):
                if (w.geo_id, x, y) not in self.visited:
                    continue
                sq = w.geo.squares[y][x]
                x0, y0 = ox + x * cell, oy + y * cell
                c.fill((40, 40, 70), (x0, y0, cell, cell))
                for d, (a, b, e, f) in ((0, (0, 0, cell, 0)), (4, (0, cell, cell, cell)),
                                        (6, (0, 0, 0, cell)), (2, (cell, 0, cell, cell))):
                    if sq.walls[d]:
                        col = (200, 200, 200) if sq.doors[d] == 0 else (230, 160, 60)
                        pygame.draw.line(c, col, (x0 + a, y0 + b), (x0 + e, y0 + f))
        px, py = ox + w.x * cell + cell // 2, oy + w.y * cell + cell // 2
        pygame.draw.circle(c, (255, 255, 85), (px, py), 2)
        pygame.draw.line(c, (255, 80, 80), (px, py), (px + DX[w.facing] * 3, py + DY[w.facing] * 3))

    def _draw_roster(self):
        s = self.scale
        x, y = (ROSTER.x + 2) * s, (ROSTER.y + 1) * s
        self.screen.blit(self.small.render('NAME', True, DIM), (x, y))
        self.screen.blit(self.small.render('AC', True, DIM), (x + 112 * s, y))
        self.screen.blit(self.small.render('HP', True, DIM), (x + 132 * s, y))
        self.screen.blit(self.small.render('EXP', True, DIM), (x + 168 * s, y))
        for n, ch in enumerate(self.world.party[:8]):
            yy = y + (9 + n * 9) * s
            col = HILITE if n == self.world.selected else TEXT
            if ch.dead or ch.hp <= 0:
                col = (240, 100, 90)
            self.screen.blit(self.font.render(ch.name[:15], True, col), (x, yy))
            self.screen.blit(self.font.render(str(ch.ac), True, col), (x + 112 * s, yy))
            hp = 'DEAD' if ch.dead else str(ch.hp)
            self.screen.blit(self.font.render(hp, True, col), (x + 132 * s, yy))
            self.screen.blit(self.font.render(str(ch.experience), True, col), (x + 168 * s, yy))
        w = self.world
        if w.geo:
            info = '%d,%d %s' % (w.x, w.y, 'N E S W'.split()[w.facing // 2])
            self.screen.blit(self.small.render(info, True, DIM), (x, (ROSTER.bottom - 8) * s))

    def _wrap(self, text, width):
        words, out, line = text.split(' '), [], ''
        for wd in words:
            t = (line + ' ' + wd).strip()
            if self.font.size(t)[0] > width and line:
                out.append(line)
                line = wd
            else:
                line = t
        if line:
            out.append(line)
        return out

    def _draw_text(self, top):
        s = self.scale
        width = 300 * s
        rows = []
        for ln in self.lines + ([self.para.strip()] if self.para.strip() else []):
            rows += self._wrap(ln, width)
        lh = 10 * s
        avail = (192 - top) * s // lh - (2 if self.menu else 0)
        rows = rows[-max(avail, 1):]
        y = top * s + 2 * s
        for r in rows:
            self.screen.blit(self.font.render(r, True, TEXT), (10 * s, y))
            y += lh
        self.menu_rects = []
        if self.menu:
            items, horiz = self.menu
            if horiz:
                x, y = 10 * s, (192 - 11) * s
                for n, it in enumerate(items):
                    surf = self.font.render(it, True, (0, 0, 0) if n == self.sel else HILITE,
                                            HILITE if n == self.sel else None)
                    if x + surf.get_width() > W * s - 8 * s:
                        x, y = 10 * s, y - lh
                    self.screen.blit(surf, (x, y))
                    self.menu_rects.append(pygame.Rect(x, y, surf.get_width(), surf.get_height()))
                    x += surf.get_width() + 12 * s
            else:
                y = top * s + 2 * s + len(rows) * lh
                for n, it in enumerate(items):
                    surf = self.font.render(it, True, (0, 0, 0) if n == self.sel else HILITE,
                                            HILITE if n == self.sel else None)
                    self.screen.blit(surf, (14 * s, y))
                    self.menu_rects.append(pygame.Rect(14 * s, y, surf.get_width(), surf.get_height()))
                    y += lh

    # ------------------------------------------------------------------ loop
    def run(self, max_frames=None, script=None):
        frames = 0
        self.pump()
        while self.running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.running = False
                elif ev.type == pygame.KEYDOWN:
                    self.key(ev)
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self.click(ev.pos)
            if script and frames in script:
                script[frames](self)
            if self.combat is not None:
                self.combat.update()
                self.end_combat_if_done()
            self.pump()
            self.draw()
            self.clock.tick(30)
            frames += 1
            if max_frames and frames >= max_frames:
                break
        pygame.quit()
