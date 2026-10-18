"""Casting spells in camp: cures, Raise Dead, Remove Curse, Detect and Read Magic.

Spells that only matter in a fight (Bless, Fireball...) are not offered
here. Raise Dead follows the manual: elves cannot be raised, and the
chance to survive it comes from constitution (Constitution Table, p.55);
a character who survives loses a point of constitution, one who does not
is gone for good.
"""
import pygame

from .inventory import Panel, ROW, TEXT, HILITE, DIM, GOOD
from .magic import heal_bonus_dice
from .spells import SPELLS

CURES = {3: (1, 8, 0), 57: (2, 8, 1), 63: (3, 8, 3)}
RAISE_DEAD = 67
REMOVE_CURSE = {43, 81, 91}
DETECT_MAGIC = {5, 11, 69, 90}
READ_MAGIC = {18}
CAMP = set(CURES) | {RAISE_DEAD} | REMOVE_CURSE | DETECT_MAGIC | READ_MAGIC
ON_SOMEONE = set(CURES) | {RAISE_DEAD} | REMOVE_CURSE
SURVIVAL = {3: 40, 4: 45, 5: 50, 6: 55, 7: 60, 8: 65, 9: 70, 10: 75, 11: 80, 12: 85, 13: 90, 14: 92,
            15: 94, 16: 96, 17: 98, 18: 100}
ELVES = (0, 1)          # Silvanesti and Qualinesti


def camp_spells(ch):
    """Distinct spells in memory this character can cast in camp."""
    out = []
    for sid in ch.spells:
        if sid in CAMP and sid not in out:
            out.append(sid)
    return out


def cast(world, caster, sid, target=None):
    """Cast a camp spell; returns the line to show. The spell leaves memory."""
    rng = world.vm.rng
    words, types = world.files.item_words(), world.files.item_types()
    name = SPELLS[sid].name
    if sid in CURES:
        if target.dead:
            return 'A cure cannot help the dead.'
        if target.hp >= target.hp_max:
            return '%s is not hurt.' % target.name
        n, size, plus = CURES[sid]
        n += heal_bonus_dice(caster)
        amount = sum(rng.randint(1, size) for _ in range(n)) + plus
        target.hp = min(target.hp_max, max(target.hp, 0) + amount)
        line = '%s casts %s on %s: +%d.' % (caster.name, name, target.name, amount)
    elif sid == RAISE_DEAD:
        if not target.dead:
            return '%s is not dead.' % target.name
        if getattr(target, 'gone', False):
            return '%s is beyond any magic.' % target.name
        race = target.raw[0x5B] if len(target.raw) > 0x5B else 6
        if race in ELVES:
            return 'The elves cannot be raised; %s rests with their people.' % target.name
        con = target.stats.get('CON', 10)
        if rng.randint(1, 100) > SURVIVAL.get(max(3, min(18, con)), 75):
            target.gone = True
            line = '%s casts Raise Dead, but %s does not survive it. %s is gone.' % (
                caster.name, target.name, target.name)
        else:
            target.dead, target.hp = False, 1
            target.stats['CON'] = max(3, con - 1)
            line = '%s raises %s from the dead!' % (caster.name, target.name)
    elif sid in REMOVE_CURSE:
        cursed = [i for i in target.items if i.cursed]
        if not cursed:
            return '%s carries nothing cursed.' % target.name
        for i in cursed:
            i.cursed = False
        line = 'The curse is lifted from %s.' % ', '.join(i.title(words, None, types) for i in cursed)
    elif sid in DETECT_MAGIC:
        found = ['%s (%s)' % (i.title(words, None, types), c.name) for c in world.party for i in c.items
                 if i.plus or i.hidden or i.effects[0]]
        line = ('Magic glows on: ' + ', '.join(found) + '.') if found else 'Nothing in the party is magical.'
    elif sid in READ_MAGIC:
        scrolls = [i for i in caster.items if 'Scroll' in i.title(words, True, types) and i.hidden]
        if not scrolls:
            return '%s has no unread scrolls.' % caster.name
        for i in scrolls:
            i.hidden = 0
        line = '%s reads %s.' % (caster.name, ', '.join(i.title(words, True, types) for i in scrolls))
    else:
        return '%s cannot be cast in camp.' % name
    caster.spells.remove(sid)
    return line


class CastView(Panel):
    TITLE = 'CAST A SPELL'

    def __init__(self, app):
        super().__init__(app)
        self.casters = [c for c in self.party if camp_spells(c)]
        self.who = 0
        self.sel = 0
        self.choosing = None        # spell waiting for its target
        self.target = 0
        self.lines = []

    @property
    def ch(self):
        return self.casters[self.who]

    def key(self, ev):
        k = ev.key
        if not self.casters:
            self.done = True
            return
        if self.choosing is not None:
            everyone = self.world.party
            if k == pygame.K_ESCAPE:
                self.choosing = None
            elif k in (pygame.K_UP, pygame.K_KP8):
                self.target = (self.target - 1) % len(everyone)
            elif k in (pygame.K_DOWN, pygame.K_KP2):
                self.target = (self.target + 1) % len(everyone)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish(everyone[self.target])
            return
        spells = camp_spells(self.ch)
        if k == pygame.K_ESCAPE:
            self.done = True
        elif k in (pygame.K_TAB, pygame.K_RIGHT, pygame.K_KP6):
            self.who, self.sel = (self.who + 1) % len(self.casters), 0
        elif k in (pygame.K_LEFT, pygame.K_KP4):
            self.who, self.sel = (self.who - 1) % len(self.casters), 0
        elif k in (pygame.K_UP, pygame.K_KP8) and spells:
            self.sel = (self.sel - 1) % len(spells)
        elif k in (pygame.K_DOWN, pygame.K_KP2) and spells:
            self.sel = (self.sel + 1) % len(spells)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and spells:
            self.start(spells[self.sel])

    def click(self, pos):
        i = self.row_at(pos)
        if i is None:
            if not self.rect.collidepoint(pos):
                self.done = True
            return
        if self.choosing is not None:
            self.target = i
            self.finish(self.world.party[i])
        else:
            spells = camp_spells(self.ch)
            if i < len(spells):
                self.sel = i
                self.start(spells[i])

    def start(self, sid):
        if sid in ON_SOMEONE:
            self.choosing, self.target = sid, 0
        else:
            self.say(cast(self.world, self.ch, sid))

    def finish(self, target):
        self.say(cast(self.world, self.ch, self.choosing, target))
        self.choosing = None

    def say(self, line):
        self.lines = (self.lines + [line])[-8:]
        self.casters = [c for c in self.party if camp_spells(c)] or self.casters
        self.who = min(self.who, len(self.casters) - 1)
        self.sel = 0

    def draw(self, screen):
        self.frame(screen)
        r = self.rect
        x, y = r.x + 40, r.y + 100
        if not self.casters:
            self.text(screen, 'No one has a spell that can be cast in camp. Press a key.', x, y, DIM)
            return
        self.tabs(screen, self.ch, x, y, self.casters)
        y += ROW + 20
        if self.choosing is not None:
            self.text(screen, 'Cast %s on whom?' % SPELLS[self.choosing].name, x, y, HILITE)
            entries = [(c.name, 'dead' if c.dead else '%d/%d' % (max(c.hp, 0), c.hp_max), TEXT)
                       for c in self.world.party]
            self.list_items(screen, entries, self.target, x, y + ROW, 900, y + ROW * 8)
        else:
            entries = [(SPELLS[s].name, 'x%d' % self.ch.spells.count(s), TEXT) for s in camp_spells(self.ch)]
            self.list_items(screen, entries, self.sel, x, y, 900, y + ROW * 8)
        yy = y + ROW * 9
        for line in self.lines:
            self.text(screen, line, x, yy, GOOD)
            yy += ROW
        self.text(screen, 'RETURN cast   TAB next caster   ESC back', x, r.bottom - 92, DIM)
