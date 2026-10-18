"""Camp: rest, heal, memorise spells, save. Opened with E (encamp)."""
import pygame

from . import magic
from .save_screen import SaveView
from .spells import SPELLS
from .world import clock_text

BOX = (30, 28, 56)
FRAME = (170, 120, 40)
TEXT = (255, 255, 255)
HILITE = (255, 255, 85)
DIM = (150, 150, 170)
GOOD = (120, 220, 120)
BAD = (240, 100, 90)
ROW = 40

MENU = (('REST', 'Rest one night'),
        ('HEAL', 'Rest until healed'),
        ('FIX', 'Fix: clerics heal, then rest as needed'),
        ('CAST', 'Cast a spell: cures, Raise Dead, Remove Curse...'),
        ('MEMORISE', 'Memorise spells'),
        ('SAVE', 'Save the game'),
        ('EXIT', 'Break camp'))
CLASS_NAME = {magic.CLERIC: 'Cleric', magic.MAGE: 'Mage'}


class CampView:
    popup = False
    over_game = True

    def __init__(self, app):
        self.app = app
        self.world = app.world
        self.sel = 0
        self.mode = 'menu'          # or 'memorise'
        self.done = False
        self.rect = pygame.Rect(0, 0, 1640, 900)
        self.rect.center = (960, 540)
        self.casters = [c for c in self.world.party if not c.dead and magic.slots(c, self.world.day)]
        self.who = 0
        self.pick = 0               # cursor in the known-spells list
        self.message = None

    # ------------------------------------------------------------ input
    def key(self, ev):
        k = ev.key
        if self.mode == 'memorise':
            self.memorise_key(ev)
            return
        if k == pygame.K_ESCAPE:
            self.done = True
        elif k in (pygame.K_UP, pygame.K_KP8, pygame.K_w):
            self.sel = (self.sel - 1) % len(MENU)
        elif k in (pygame.K_DOWN, pygame.K_KP2, pygame.K_s):
            self.sel = (self.sel + 1) % len(MENU)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.choose(MENU[self.sel][0])
        elif ev.unicode:
            for i, (word, _) in enumerate(MENU):
                if word[0] == ev.unicode.upper():
                    self.sel = i
                    self.choose(word)
                    break

    def click(self, pos):
        if self.mode == 'menu':
            i = (pos[1] - self.rect.y - 120) // ROW
            if self.rect.collidepoint(pos) and 0 <= i < len(MENU) and pos[0] < self.rect.x + 700:
                self.sel = i
                self.choose(MENU[i][0])
        else:
            for i, r in enumerate(getattr(self, 'known_rects', [])):
                if r.collidepoint(pos):
                    self.pick = i
                    self.add()
                    return
            for i, r in enumerate(getattr(self, 'chosen_rects', [])):
                if r.collidepoint(pos):
                    self.remove(i)
                    return

    def choose(self, word):
        if word in ('REST', 'HEAL', 'FIX'):
            self.done = True
            self.app.start_camp({'REST': 'rest', 'HEAL': 'heal', 'FIX': 'fix'}[word])
        elif word == 'CAST':
            from .camp_magic import CastView
            self.done = True
            self.app.overlay_next = CastView(self.app)
        elif word == 'MEMORISE':
            if not self.casters:
                self.message = 'No one in the party casts spells.'
                return
            self.mode, self.pick = 'memorise', 0
        elif word == 'SAVE':
            self.done = True
            self.app.overlay_next = SaveView(self.app, 'save')
        else:
            self.done = True

    # --- memorise --------------------------------------------------------------
    @property
    def ch(self):
        return self.casters[self.who]

    def options(self):
        k = magic.known(self.ch)
        return k[magic.CLERIC] + k[magic.MAGE]

    def memorise_key(self, ev):
        k = ev.key
        opts = self.options()
        if k == pygame.K_ESCAPE:
            self.mode, self.message = 'menu', None
        elif k in (pygame.K_TAB, pygame.K_RIGHT, pygame.K_KP6):
            self.who = (self.who + 1) % len(self.casters)
            self.pick, self.message = 0, None
        elif k in (pygame.K_LEFT, pygame.K_KP4):
            self.who = (self.who - 1) % len(self.casters)
            self.pick, self.message = 0, None
        elif k in (pygame.K_UP, pygame.K_KP8, pygame.K_w) and opts:
            self.pick = (self.pick - 1) % len(opts)
        elif k in (pygame.K_DOWN, pygame.K_KP2, pygame.K_s) and opts:
            self.pick = (self.pick + 1) % len(opts)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.add()
        elif k in (pygame.K_BACKSPACE, pygame.K_DELETE):
            self.remove(None)
        elif ev.unicode.lower() == 'c':
            self.ch.memorised = []
            self.message = 'Choices cleared.'

    def add(self):
        opts = self.options()
        if not opts:
            return
        sid = opts[self.pick % len(opts)]
        want = self.ch.memorised + [sid]
        kept, dropped = magic.fit(self.ch, want, self.world.day)
        if dropped:
            sp = SPELLS[sid]
            self.message = 'No %s level %d slot left.' % (CLASS_NAME[sp.cls].lower(), sp.level)
            return
        self.ch.memorised = kept
        self.message = None

    def remove(self, i):
        m = self.ch.memorised
        if not m:
            return
        m.pop(len(m) - 1 if i is None else i)     # what is in memory stays until the next rest
        self.message = None

    # ------------------------------------------------------------ drawing
    def draw(self, screen):
        r = self.rect
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, BOX, r)
        pygame.draw.rect(screen, FRAME, r, 4)
        font, small = self.app.font, self.app.small
        title = 'CAMP' if self.mode == 'menu' else 'MEMORISE SPELLS'
        screen.blit(font.render(title, True, HILITE), (r.x + 40, r.y + 30))
        t = small.render(clock_text(self.world.minutes), True, DIM)
        screen.blit(t, (r.right - 40 - t.get_width(), r.y + 38))
        if self.mode == 'menu':
            self.draw_menu(screen, font, small)
        else:
            self.draw_memorise(screen, font, small)
        if self.message:
            screen.blit(small.render(self.message, True, BAD), (r.x + 40, r.bottom - 56))

    def draw_menu(self, screen, font, small):
        r = self.rect
        y = r.y + 120
        for i, (word, text) in enumerate(MENU):
            col = HILITE if i == self.sel else TEXT
            if i == self.sel:
                pygame.draw.rect(screen, (60, 60, 110), (r.x + 24, y - 4, 660, ROW - 2))
            screen.blit(small.render(word[0], True, HILITE), (r.x + 40, y))
            screen.blit(small.render(text, True, col), (r.x + 80, y))
            y += ROW
        # the party and the moons
        x, y = r.x + 760, r.y + 120
        screen.blit(small.render('PARTY', True, DIM), (x, y))
        y += ROW
        for c in self.world.party:
            col = BAD if c.dead or c.hp <= 0 else (TEXT if c.hp >= c.hp_max else HILITE)
            hp = 'dead' if c.dead else '%d/%d' % (max(c.hp, 0), c.hp_max)
            screen.blit(small.render(c.name[:16], True, col), (x, y))
            screen.blit(small.render(hp, True, col), (x + 330, y))
            if magic.slots(c, self.world.day):
                ready = magic.fit(c, c.memorised, self.world.day)[0]
                n = len(c.spells)
                screen.blit(small.render('spells %d/%d' % (n, len(ready)), True,
                                         GOOD if n >= len(ready) else DIM), (x + 480, y))
            y += ROW
        y += 24
        screen.blit(small.render('THE MOONS', True, DIM), (x, y))
        y += ROW
        for order, (name, _) in sorted(magic.MOONS.items()):
            phase = magic.moon_phase(order, self.world.day)
            screen.blit(small.render('%-9s %s' % (name, phase), True, TEXT), (x, y))
            y += ROW - 4
        screen.blit(small.render('Rest heals each character a little every night and brings back',
                                 True, DIM), (r.x + 40, r.bottom - 140))
        screen.blit(small.render('the spells chosen in Memorise. A night may be interrupted.',
                                 True, DIM), (r.x + 40, r.bottom - 106))

    def draw_memorise(self, screen, font, small):
        r, ch, day = self.rect, self.ch, self.world.day
        x, y = r.x + 40, r.y + 100
        names = '   '.join(('[%s]' if c is ch else '%s') % c.name for c in self.casters)
        screen.blit(small.render(names, True, TEXT), (x, y))
        y += ROW + 10
        # slots and choices
        sl = magic.slots(ch, day)
        use = magic.used(ch, ch.memorised, day)
        top = y
        for key in sorted(sl, key=lambda k: (k[0], 99 if k[1] == 'bonus' else k[1])):
            cls, lvl = key
            label = ('%s level %d' % (CLASS_NAME[cls], lvl)) if lvl != 'bonus' else 'Mage moon bonus (any level)'
            col = GOOD if use[key] == sl[key] else TEXT
            screen.blit(small.render('%s: %d of %d' % (label, use[key], sl[key]), True, col), (x, y))
            y += ROW - 6
        y += 16
        screen.blit(small.render('CHOSEN (click or BACKSPACE to remove)', True, DIM), (x, y))
        y += ROW
        in_mem = list(ch.spells)
        self.chosen_rects = []
        for sid in ch.memorised:
            ready = sid in in_mem
            if ready:
                in_mem.remove(sid)
            t = small.render('%s%s' % (SPELLS[sid].name, '' if ready else '   (after a rest)'),
                             True, TEXT if ready else HILITE)
            screen.blit(t, (x + 20, y))
            self.chosen_rects.append(pygame.Rect(x + 20, y, 600, ROW - 6))
            y += ROW - 6
            if y > r.bottom - 120:
                break
        # what can be chosen
        x2, y = r.x + 860, top
        screen.blit(small.render('KNOWN SPELLS (RETURN or click to add)', True, DIM), (x2, y))
        y += ROW
        self.known_rects = []
        for i, sid in enumerate(self.options()):
            sp = SPELLS[sid]
            if i == self.pick:
                pygame.draw.rect(screen, (60, 60, 110), (x2 - 10, y - 4, 720, ROW - 6))
            col = HILITE if i == self.pick else (TEXT if sp.combat else DIM)
            screen.blit(small.render('%s %d  %s' % (sp.cls, sp.level, sp.name), True, col), (x2, y))
            self.known_rects.append(pygame.Rect(x2 - 10, y - 4, 720, ROW - 6))
            y += ROW - 6
            if y > r.bottom - 100:
                break
        save, extra, level = magic.moon_effect(ch, day)
        if ch.levels.get('magic-user'):
            moon = magic.MOONS.get(ch.raw[0x5F], ('no moon', 0))[0]
            note = '%s is %s: %+d spells, saves %+d, level %+d' % (
                moon, magic.moon_phase(ch.raw[0x5F], day) or '-', extra, save, level)
            screen.blit(small.render(note, True, DIM), (r.x + 40, r.bottom - 96))
        screen.blit(small.render('TAB / arrows: next caster   C: clear   ESC: back', True, DIM),
                    (r.x + 860, r.bottom - 56))
