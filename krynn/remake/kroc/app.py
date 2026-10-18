"""pygame front end: draws the original graphics, drives the ECL VM."""
import os
import time

import pygame

from cok import gfx, view3d
from cok.geo import DX, DY

from . import encounter
from .combat_screen import CombatScreen
from . import savegame
from .journal import Journal, JournalView
from .save_screen import SaveView
from .camp_screen import CampView
from .inventory import ItemsView, ShopView, TempleView, TreasureView
from .world import SHOP_FLAG, TEMPLE_FLAG
from .world import World, OVERLAND_X, OVERLAND_Y

# Everything is drawn on a 1920x1080 frame, then fitted to the window.
# Original pictures are enlarged by whole numbers only, so the pixel art
# stays crisp; text and panels are laid out at full resolution.
W, H = 1920, 1080
FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts', 'PixelifySans.ttf')

BG = (16, 16, 40)
FRAME = (170, 120, 40)
TEXT = (255, 255, 255)
HILITE = (255, 255, 85)
DIM = (150, 150, 170)

VIEW_ZOOM = 7                                   # 88x88 3D view / portraits
VIEW = pygame.Rect(40, 40, 88 * VIEW_ZOOM, 88 * VIEW_ZOOM)
BIG_ZOOM = 5                                    # 304x120 big pictures, overland map
BIG = pygame.Rect((W - 304 * BIG_ZOOM) // 2, 40, 304 * BIG_ZOOM, 120 * BIG_ZOOM)
ROSTER = pygame.Rect(VIEW.right + 40, 40, 800, VIEW.h)
MAP = pygame.Rect(ROSTER.right + 32, 40, W - 40 - ROSTER.right - 32, W - 40 - ROSTER.right - 32)
TEXT_TOP = VIEW.bottom + 40                     # text box under the view
TEXT_TOP_BIG = BIG.bottom + 40                  # ... under a big picture
TEXT_BOTTOM = H - 40
FONT_SIZE, SMALL_SIZE = 38, 28
LINE = 48

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
    def __init__(self, source=None, size=None, fullscreen=False):
        pygame.init()
        pygame.display.set_caption('Champions of Krynn - remake')
        self.fullscreen = fullscreen
        self.window_size = size or self.default_size()
        self.window = self.open_window()
        self.screen = pygame.Surface((W, H))          # the 1920x1080 frame
        self.font = pygame.font.Font(FONT, FONT_SIZE)
        self.small = pygame.font.Font(FONT, SMALL_SIZE)
        self.tiny = pygame.font.Font(FONT, 20)
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
        self.overlay = None         # JournalView while reading
        self.journal = Journal()
        self.journal_button = pygame.Rect(0, 0, 0, 0)
        self.overlay_next = None    # a screen to open when the current one closes
        self.seen_refs = set()      # references already shown from the current text
        self.wait_until = 0
        self.visited = set()
        self.cache = {}
        self.gen = self.world.start()
        self.answer = None
        self.running = True

    # ------------------------------------------------------------------ window
    @staticmethod
    def default_size():
        """1920x1080 when it fits, else the largest 16:9 window that does."""
        info = pygame.display.Info()
        dw, dh = info.current_w or W, info.current_h or H
        if dw >= W and dh >= H + 60:
            return W, H
        k = min(dw * 0.92 / W, dh * 0.85 / H)
        return max(640, int(W * k)), max(360, int(H * k))

    def open_window(self):
        if self.fullscreen:
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        return pygame.display.set_mode(self.window_size, pygame.RESIZABLE)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.window = self.open_window()

    def fit(self):
        """(scale, offset) placing the frame in the window, letterboxed."""
        ww, wh = self.window.get_size()
        k = min(ww / W, wh / H)
        return k, ((ww - int(W * k)) // 2, (wh - int(H * k)) // 2)

    def to_frame(self, pos):
        k, (ox, oy) = self.fit()
        return int((pos[0] - ox) / k), int((pos[1] - oy) / k)

    def present(self):
        k, (ox, oy) = self.fit()
        if k == 1:
            self.window.blit(self.screen, (ox, oy))
        else:
            self.window.fill((0, 0, 0))
            size = (int(W * k), int(H * k))
            img = pygame.transform.smoothscale(self.screen, size) if k < 1 else \
                pygame.transform.scale(self.screen, size)
            self.window.blit(img, (ox, oy))
        pygame.display.flip()

    def save_frame(self, path):
        pygame.image.save(self.screen, path)

    # ------------------------------------------------------------------ util
    def log(self, text):
        self.notes.append(text)
        self.add_text(text, False)

    def add_text(self, text, clear):
        if clear:
            self.lines, self.para = [], ''
            self.seen_refs = set()
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
        while self.gen and not self.menu and not self.combat and not self.overlay and time.time() >= self.wait_until:
            try:
                req = self.gen.send(self.answer)
            except StopIteration:
                self.gen = None
                self.flush()
                self.check_journal()
                break
            self.answer = None
            k = req[0]
            if k == 'print':
                self.add_text(req[1], req[2])
            elif k == 'menu':
                self.flush()
                self.menu, self.sel = (req[1], req[2]), 0
                self.check_journal()
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
                self.seen_refs = set()
            elif k == 'delay':
                self.wait_until = time.time() + 0.6
            elif k == 'combat':
                self.flush()
                vm = self.world.vm
                if vm.get(SHOP_FLAG) == 1:            # the scripts open shops and temples
                    vm.set(SHOP_FLAG, 0)              # through COMBAT with a flag set
                    self.overlay = ShopView(self, self.world.shop_stock)
                    self.answer = True
                elif vm.get(TEMPLE_FLAG) == 1:
                    vm.set(TEMPLE_FLAG, 0)
                    self.overlay = TempleView(self)
                    self.answer = True
                elif not req[1]:
                    self.answer = True                # nothing to fight
                else:
                    self.combat = CombatScreen(self, encounter.build(self.world, req[1], self.world.vm.rng))
            elif k == 'program':
                if req[1] == 9:
                    self.world.rest()
                    self.add_text('The party rests and recovers.', False)
                    self.flush()
            elif k == 'treasure':
                found, items = self.world.treasure(req[1])
                if found or items:
                    self.overlay = TreasureView(self, found, items)
            elif k == 'note':
                print('[ecl]', req[1])
            elif k == 'block':
                self.picture = None
                self.sprite = None
            elif k == 'redraw':
                pass
        if self.world.in_dungeon and self.world.geo:
            self.visited.add((self.world.geo_id, self.world.x, self.world.y))

    def check_journal(self):
        """Open the page of any journal entry / tavern tale the text just mentioned."""
        text = ' '.join(self.lines + [self.para])
        for ref in Journal.references(text):
            if ref in self.seen_refs:
                continue
            self.seen_refs.add(ref)
            if ref not in self.world.journal_found:
                self.world.journal_found.append(ref)
            self.overlay = JournalView(self, self.journal, self.world.journal_found, ref, popup=True)
            return

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
            self.toggle_fullscreen()
            return
        if self.combat is not None:
            self.combat.key(ev)
            self.end_combat_if_done()
            return
        if self.overlay is not None:
            popup = self.overlay.popup
            self.overlay.key(ev)
            if self.overlay.done:
                self.overlay, self.overlay_next = self.overlay_next, None
                if popup and ev.key == pygame.K_j:
                    self.open_journal()
            return
        if ev.key == pygame.K_j:
            self.open_journal()
            return
        if ev.key == pygame.K_F5:
            if self.busy():
                self.notify('Finish what you are doing first: you can save when the party is free to move.')
            else:
                self.overlay = SaveView(self, 'save')
            return
        if ev.key == pygame.K_i and not self.combat:
            self.overlay = ItemsView(self, self.world.selected)
            return
        if ev.key == pygame.K_e:
            if self.busy():
                self.notify('You cannot make camp in the middle of things.')
            else:
                self.overlay = CampView(self)
            return
        if ev.key == pygame.K_F9:
            self.overlay = SaveView(self, 'load')
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
        if ev.key in KEYS:
            self.act(KEYS[ev.key])

    # ------------------------------------------------------------------ saving
    def busy(self):
        """True while a script is waiting on the player (text, menu, fight)."""
        return bool(self.gen or self.menu or self.combat)

    def notify(self, text):
        self.add_text(text, False)
        self.flush()

    def save_game(self, slot):
        savegame.save(slot, self.world, self.visited)
        self.notify('Game saved in slot %s.' % slot)

    def start_camp(self, mode):
        self.picture = self.sprite = None
        self.gen = self.world.camp(mode)
        self.answer = None
        self.pump()

    def load_game(self, slot):
        world, visited = savegame.load(slot, self.world.files, self.log)
        self.world, self.visited = world, visited
        self.overlay_next = None
        self.gen = self.menu = self.combat = None
        self.answer = None
        self.picture = self.sprite = None
        self.lines, self.para = [], ''
        self.seen_refs = set()
        self.wait_until = 0
        self.notify('Game %s loaded: %s.' % (slot, savegame.describe(world)))

    def end_combat_if_done(self):
        if self.combat is not None and self.combat.done:
            result = self.combat.b.result
            self.combat = None
            if result == 'lost':
                # the party is dead: back to the start, as the original does
                self.world = World(files=self.world.files, log=self.log)
                self.lines, self.para, self.picture, self.sprite = [], '', None, None
                self.add_text('The party has perished. A new band gathers at the Inn... '
                              '(F9 loads a saved game.)', True)
                self.flush()
                self.gen = self.world.start()
                self.answer = None
            else:
                self.answer = result == 'won'
            self.pump()

    def open_journal(self):
        last = self.world.journal_found[-1] if self.world.journal_found else None
        self.overlay = JournalView(self, self.journal, self.world.journal_found, last)

    def click(self, pos):
        if self.overlay is not None:
            self.overlay.click(pos)
            if self.overlay.done:
                self.overlay, self.overlay_next = self.overlay_next, None
            return
        if self.journal_button.collidepoint(pos) and self.combat is None:
            self.open_journal()
            return
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
        if self.overlay is not None and not getattr(self.overlay, 'over_game', False):
            self.overlay.draw(self.screen)
            self.present()
            return
        if self.overlay is not None:
            overlay, self.overlay = self.overlay, None      # the game underneath, then the box
            try:
                self.draw_game()
            finally:
                self.overlay = overlay
            overlay.draw(self.screen)
            self.present()
            return
        self.draw_game()
        self.present()

    def draw_game(self):
        if self.combat is not None:
            self.combat.draw(self.screen)
            return
        c = self.screen
        c.fill(BG)
        w = self.world
        big = self.picture and self.picture[1] == 'big'
        overland = not w.in_dungeon and not self.picture and self.pic(0x79) is not None
        if big or overland:
            p = self.picture[0] if big else self.pic(0x79)
            self.blit_zoomed(surface_from(p, self._frame(p)), BIG.topleft, BIG_ZOOM)
            pygame.draw.rect(c, FRAME, BIG.inflate(12, 12), 3)
            if overland:
                x, y = w.vm.get(OVERLAND_X), w.vm.get(OVERLAND_Y)
                if int(time.time() * 3) % 2:
                    cell = 8 * BIG_ZOOM
                    pygame.draw.rect(c, (255, 255, 255), (BIG.x + x * cell, BIG.y + y * cell, cell, cell), 4)
            text_top = TEXT_TOP_BIG
        else:
            self._draw_view()
            pygame.draw.rect(c, FRAME, VIEW.inflate(12, 12), 3)
            pygame.draw.rect(c, FRAME, ROSTER.inflate(12, 12), 3)
            self._draw_roster()
            self._draw_map()
            text_top = TEXT_TOP
        pygame.draw.rect(c, FRAME, (VIEW.x - 6, text_top - 6, W - 2 * VIEW.x + 12, TEXT_BOTTOM - text_top + 12), 3)
        self._draw_text(text_top)
        self._draw_journal_button()

    def _draw_journal_button(self):
        n = len(self.world.journal_found)
        label = ' JOURNAL (J)  %d ' % n
        t = self.small.render(label, True, (0, 0, 0), (200, 170, 90))
        r = t.get_rect(bottomright=(W - 46, TEXT_BOTTOM - 10))
        self.screen.blit(t, r)
        self.journal_button = r

    def blit_zoomed(self, surf, pos, zoom):
        w, h = surf.get_size()
        self.screen.blit(pygame.transform.scale(surf, (w * zoom, h * zoom)), pos)

    def _frame(self, p):
        if len(p.frames) == 1 or not self.picture:
            return 0
        t = time.time() - self.picture[2]
        n = len(p.frames) - 1
        return 1 + int(t * 4) % n if t > 0.5 else 0

    def _draw_view(self):
        w = self.world
        if self.picture and self.picture[1] == 'pic':
            p = self.picture[0]
            self.blit_zoomed(surface_from(p, self._frame(p)), VIEW.topleft, VIEW_ZOOM)
        elif w.geo and w.slots:
            buf = self.renderer.render(w.geo, w.x, w.y, w.facing, w.slots)
            self.blit_zoomed(indexed_surface(buf, 88, 88, gfx.EGA * 2), VIEW.topleft, VIEW_ZOOM)
        else:
            self.screen.fill((0, 0, 0), VIEW)
        if self.sprite:
            sp, dist = self.sprite
            key = gfx.transparent_index(sp)
            self.blit_zoomed(surface_from(sp, dist, key), VIEW.topleft, VIEW_ZOOM)

    def _draw_map(self):
        """Automap of the squares visited on this map (always shown)."""
        c, w = self.screen, self.world
        pygame.draw.rect(c, FRAME, MAP.inflate(12, 12), 3)
        c.fill((0, 0, 0), MAP)
        if not (w.in_dungeon and w.geo):
            t = self.small.render('no map here', True, DIM)
            c.blit(t, t.get_rect(center=MAP.center))
            return
        cell = (MAP.w - 16) // 16
        ox, oy = MAP.x + 8, MAP.y + 8
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
                        pygame.draw.line(c, col, (x0 + a, y0 + b), (x0 + e, y0 + f), 3)
        px, py = ox + w.x * cell + cell // 2, oy + w.y * cell + cell // 2
        pygame.draw.circle(c, (255, 255, 85), (px, py), cell // 4)
        pygame.draw.line(c, (255, 80, 80), (px, py),
                         (px + DX[w.facing] * cell // 2, py + DY[w.facing] * cell // 2), 4)
        info = '%d,%d facing %s' % (w.x, w.y, 'NORTH EAST SOUTH WEST'.split()[w.facing // 2])
        t = self.small.render(info, True, DIM)
        c.blit(t, (MAP.x, MAP.bottom + 24))
        hint = self.small.render('arrows move, L search, E camp', True, DIM)
        c.blit(hint, (MAP.x, MAP.bottom + 24 + 36))

    def _draw_roster(self):
        c = self.screen
        x, y = ROSTER.x + 20, ROSTER.y + 16
        cols = (0, 430, 530, 690)
        for col, head in zip(cols, ('NAME', 'AC', 'HP', 'EXP')):
            c.blit(self.small.render(head, True, DIM), (x + col, y))
        for n, ch in enumerate(self.world.party[:8]):
            yy = y + 48 + n * 60
            colr = HILITE if n == self.world.selected else TEXT
            if ch.dead or ch.hp <= 0:
                colr = (240, 100, 90)
            hp = 'DEAD' if ch.dead else '%d/%d' % (ch.hp, ch.hp_max)
            for col, val in zip(cols, (ch.name[:16], str(ch.ac), hp, str(ch.experience))):
                c.blit(self.font.render(val, True, colr), (x + col, yy))

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
        c = self.screen
        left, width = VIEW.x + 20, W - 2 * VIEW.x - 40
        rows = []
        for ln in self.lines + ([self.para.strip()] if self.para.strip() else []):
            rows += self._wrap(ln, width)
        bottom = TEXT_BOTTOM - 12
        menu_h = LINE + 8 if self.menu and self.menu[1] else 0
        avail = max(1, (bottom - top - 12 - menu_h) // LINE - (len(self.menu[0]) if self.menu and not self.menu[1] else 0))
        rows = rows[-avail:]
        y = top + 12
        for r in rows:
            c.blit(self.font.render(r, True, TEXT), (left, y))
            y += LINE
        self.menu_rects = []
        if self.menu:
            items, horiz = self.menu
            if horiz:
                x, y = left, bottom - LINE
                for n, it in enumerate(items):
                    surf = self.font.render(' %s ' % it, True, (0, 0, 0) if n == self.sel else HILITE,
                                            HILITE if n == self.sel else None)
                    if x + surf.get_width() > left + width:
                        x, y = left, y - LINE
                    c.blit(surf, (x, y))
                    self.menu_rects.append(pygame.Rect(x, y, surf.get_width(), surf.get_height()))
                    x += surf.get_width() + 32
            else:
                for n, it in enumerate(items):
                    surf = self.font.render(' %s ' % it, True, (0, 0, 0) if n == self.sel else HILITE,
                                            HILITE if n == self.sel else None)
                    c.blit(surf, (left + 24, y))
                    self.menu_rects.append(pygame.Rect(left + 24, y, surf.get_width(), surf.get_height()))
                    y += LINE

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
                    self.click(self.to_frame(ev.pos))
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3 and self.combat is not None:
                    self.combat.cancel()
                elif ev.type == pygame.MOUSEMOTION and self.combat is not None:
                    self.combat.motion(self.to_frame(ev.pos))
                elif ev.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self.window_size = ev.size
                    self.window = self.open_window()
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
