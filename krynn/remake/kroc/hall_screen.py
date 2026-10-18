"""The training hall: level up, and mages choose a new grimoire spell."""
import pygame

from . import training as T
from .inventory import Panel, ROW, TEXT, HILITE, DIM, GOOD
from .spells import SPELLS

SHORT = {'cleric': 'Cleric', 'druid': 'Druid', 'fighter': 'Fighter', 'paladin': 'Paladin', 'ranger': 'Ranger',
         'magic-user': 'Mage', 'thief': 'Thief', 'knight': 'Knight'}


class HallView(Panel):
    TITLE = 'TRAINING HALL'

    def __init__(self, app):
        super().__init__(app)
        self.sel = 0
        self.picking = False        # choosing a grimoire spell
        self.pick = 0
        self.lines = []

    @property
    def ch(self):
        return self.party[self.sel]

    def key(self, ev):
        k = ev.key
        if self.picking:
            self.pick_key(k)
            return
        if k == pygame.K_ESCAPE:
            self.done = True
        elif k in (pygame.K_UP, pygame.K_KP8, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.party)
        elif k in (pygame.K_DOWN, pygame.K_KP2, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.party)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_t):
            self.train()
        elif k == pygame.K_g and self.ch.spell_picks:
            self.start_picking()

    def click(self, pos):
        i = self.row_at(pos)
        if i is None:
            if not self.rect.collidepoint(pos):
                self.done = True
            return
        if self.picking:
            self.pick = i
            self.choose()
        elif i == self.sel:
            self.train()
        else:
            self.sel = i

    def train(self):
        ch = self.ch
        lines = T.train(ch, self.world.vm.rng)
        if not lines:
            needs = ['%s %d at %d XP' % (SHORT[c], ch.levels[c] + 1, T.next_level_xp(ch, c))
                     for c in T.classes(ch) if T.next_level_xp(ch, c) is not None]
            self.message = ('%s needs more experience: %s.' % (ch.name, ', '.join(needs)) if needs
                            else '%s has reached the highest level this game allows.' % ch.name)
            return
        self.message = None
        ch.refresh(self.types, self.words)
        self.lines = (self.lines + lines)[-6:]
        if ch.spell_picks:
            self.start_picking()

    # --- a new spell for the grimoire -------------------------------------------------
    def start_picking(self):
        if not T.learnable(self.ch, self.world.day):
            self.ch.spell_picks = 0
            self.lines.append('%s already knows every spell open to the order.' % self.ch.name)
            return
        self.picking, self.pick = True, 0

    def pick_key(self, k):
        opts = T.learnable(self.ch, self.world.day)
        if k == pygame.K_ESCAPE:
            self.picking = False            # chosen later, at any hall
        elif k in (pygame.K_UP, pygame.K_KP8) and opts:
            self.pick = (self.pick - 1) % len(opts)
        elif k in (pygame.K_DOWN, pygame.K_KP2) and opts:
            self.pick = (self.pick + 1) % len(opts)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.choose()

    def choose(self):
        ch = self.ch
        opts = T.learnable(ch, self.world.day)
        if not opts:
            self.picking = False
            return
        sid = opts[self.pick % len(opts)]
        ch.book.append(sid)
        ch.spell_picks -= 1
        self.lines.append('%s scribes %s into the grimoire.' % (ch.name, SPELLS[sid].name))
        self.picking = ch.spell_picks > 0 and bool(T.learnable(ch, self.world.day))
        self.pick = 0

    # --- drawing ------------------------------------------------------------------------
    def draw(self, screen):
        self.frame(screen)
        r = self.rect
        x, y = r.x + 40, r.y + 100
        if self.picking:
            self.text(screen, '%s chooses a new spell for the grimoire:' % self.ch.name, x, y, HILITE)
            entries = [('%d  %s' % (SPELLS[s].level, SPELLS[s].name), '', TEXT)
                       for s in T.learnable(self.ch, self.world.day)]
            self.list_items(screen, entries, self.pick, x, y + ROW + 10, 900, r.bottom - 120)
            self.text(screen, 'RETURN choose   ESC later', x, r.bottom - 92, DIM)
            return
        self.text(screen, 'Training is free. Each class with enough experience goes up a level.',
                  x, y, DIM)
        entries = []
        for c in self.party:
            levels = '/'.join('%s %d' % (SHORT[k], c.levels[k]) for k in T.classes(c))
            ready = T.ready(c)
            nxt = [T.next_level_xp(c, k) for k in T.classes(c)]
            nxt = min([n for n in nxt if n is not None] or [0])
            right = 'READY TO TRAIN' if ready else ('next at %d' % nxt if nxt else 'top level')
            if c.spell_picks:
                right += ', G: new spell'
            entries.append(([(0, c.name), (380, levels), (1000, '%d XP' % c.experience)], right,
                            GOOD if ready else TEXT))
        self.list_items(screen, entries, self.sel, x, y + ROW + 10, 1640, y + ROW * 9)
        yy = y + ROW * 9 + 20
        for line in self.lines:
            self.text(screen, line, x, yy, GOOD)
            yy += ROW
        self.text(screen, 'RETURN/T train   G choose a grimoire spell   ESC leave', x, r.bottom - 92, DIM)
