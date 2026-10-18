"""The character sheet (V) and character creation (at a hall, or krynn.py --new)."""
import pygame

from . import creation as C, magic, training as T
from .art import Art
from .inventory import Panel, ROW, TEXT, HILITE, DIM, GOOD, BAD
from .spells import SPELLS

SHORT = {'cleric': 'Cleric', 'druid': 'Druid', 'fighter': 'Fighter', 'paladin': 'Paladin', 'ranger': 'Ranger',
         'magic-user': 'Mage', 'thief': 'Thief', 'knight': 'Knight'}
MAX_PARTY = 6


def classes_text(ch):
    return '/'.join(SHORT[c] for c in T.classes(ch)), '/'.join(str(ch.levels[c]) for c in T.classes(ch))


def strength_text(ch):
    st = ch.stats.get('STR', 0)
    extra = ch.raw[0x1C] if len(ch.raw) > 0x1C else 0
    return '18/%02d' % (extra % 100) if st == 18 and extra else str(st)


class SheetView(Panel):
    TITLE = 'CHARACTER'

    def __init__(self, app, who=0):
        super().__init__(app)
        self.who = min(who, len(self.world.party) - 1)
        self.art = Art(self.world, app.small)

    @property
    def ch(self):
        return self.world.party[self.who]

    def key(self, ev):
        if ev.key in (pygame.K_ESCAPE, pygame.K_v, pygame.K_RETURN):
            self.done = True
        elif ev.key in (pygame.K_TAB, pygame.K_RIGHT, pygame.K_DOWN):
            self.who = (self.who + 1) % len(self.world.party)
        elif ev.key in (pygame.K_LEFT, pygame.K_UP):
            self.who = (self.who - 1) % len(self.world.party)

    def click(self, pos):
        if not self.rect.collidepoint(pos):
            self.done = True
        else:
            self.who = (self.who + 1) % len(self.world.party)

    def draw(self, screen):
        ch = self.ch
        self.frame(screen, ch.name)
        r = self.rect
        self.tabs(screen, ch, r.x + 40, r.y + 92, self.world.party)
        icon = self.art._compose(ch.icon)
        if icon is not None:
            screen.blit(pygame.transform.scale(icon, (144, 144)), (r.right - 200, r.y + 150))
        x, y = r.x + 40, r.y + 150
        names, levels = classes_text(ch)
        race = T.RACES[ch.raw[0x5B]] if len(ch.raw) > 0x5B and ch.raw[0x5B] < 7 else ''
        align = C.ALIGNMENTS[ch.alignment] if getattr(ch, 'alignment', None) is not None else ''
        lines = [(race.title() + ('  ' + align if align else ''), HILITE), ('%s  %s' % (names, levels), TEXT)]
        status = 'GONE' if getattr(ch, 'gone', False) else ('DEAD' if ch.dead else (
            'UNCONSCIOUS' if ch.hp <= 0 else 'OKAY'))
        lines.append(('Status: ' + status, BAD if status != 'OKAY' else GOOD))
        nxt = [T.next_level_xp(ch, c) for c in T.classes(ch)]
        nxt = min([n for n in nxt if n] or [0])
        lines.append(('Experience %d%s' % (ch.experience, ('   next level at %d' % nxt) if nxt else ''), TEXT))
        lines.append(('', TEXT))
        for i, s in enumerate(C.STATS):
            val = strength_text(ch) if s == 'STR' else str(ch.stats.get(s, 0))
            lines.append(('%s %s' % (s, val), TEXT))
        for text, col in lines:
            self.text(screen, text, x, y, col)
            y += ROW
        # combat figures
        x2, y = r.x + 620, r.y + 150
        n, size, bonus = ch.weapon
        figures = ['Hit points %d/%d' % (max(ch.hp, 0), ch.hp_max), 'Armour class %d' % ch.ac,
                   'THAC0 %d' % ch.thac0, 'Damage %dd%d%s' % (n, size, ('%+d' % bonus) if bonus else ''),
                   'Save vs spells %d' % ch.save_spell, 'Movement %d' % ch.move]
        god = magic.GODS.get(magic.deity(ch))
        if god:
            figures.append('Cleric of %s' % god)
        if ch.levels.get('knight'):
            figures.append('Knight of the %s' % T.ORDERS[max(1, ch.raw[0x5D]) - 1])
        if ch.levels.get('magic-user') and len(ch.raw) > 0x5F and ch.raw[0x5F] in magic.MOONS:
            moon = magic.MOONS[ch.raw[0x5F]][0]
            figures.append('%s Robes: %s %s' % (('White', 'Red', 'Black')[ch.raw[0x5F] - 1], moon,
                                                 magic.moon_phase(ch.raw[0x5F], self.world.day)))
        for text in figures:
            self.text(screen, text, x2, y, TEXT)
            y += ROW
        y += 10
        self.text(screen, 'READIED', x2, y, DIM)
        y += ROW
        for it in [i for i in ch.items if i.ready][:6]:
            self.text(screen, it.title(self.words, None, self.types), x2 + 20, y, TEXT)
            y += ROW - 4
        if ch.spells:
            y += 10
            names = sorted({SPELLS[s].name for s in ch.spells if s in SPELLS})
            self.text(screen, 'SPELLS IN MEMORY', x2, y, DIM)
            y += ROW
            line = ''
            for nm in names:
                if self.app.small.size(line + nm)[0] > 900:
                    self.text(screen, line, x2 + 20, y, TEXT)
                    y, line = y + ROW - 4, ''
                line += nm + ', '
            self.text(screen, line.rstrip(', '), x2 + 20, y, TEXT)
        self.text(screen, 'TAB / arrows: next character   ESC: close', r.x + 40, r.bottom - 92, DIM)


class CreateView(Panel):
    """Make a character, one choice at a time; with new_party, a whole party."""
    TITLE = 'NEW CHARACTER'
    STEPS = ('race', 'class', 'alignment', 'god', 'abilities', 'name')

    def __init__(self, app, new_party=False):
        super().__init__(app)
        self.new_party = new_party
        self.art = Art(self.world, app.small)
        self.rng = self.world.vm.rng
        self.made = []
        self.reset()

    def reset(self):
        self.step, self.sel = 'race', 0
        self.race = self.combo = self.alignment = None
        self.god = 0
        self.stats = None
        self.name = ''
        self.icon = {'head': self.rng.randint(0, 8), 'body': self.rng.choice((1, 11, 14, 24, 28)),
                     'colours': bytes(self.rng.randint(0, 255) for _ in range(6)), 'size': 2}

    # --- the options of each step --------------------------------------------------
    def options(self):
        if self.step == 'race':
            return [(r, T.RACES[r].title()) for r in (6, 0, 1, 2, 3, 4, 5)]
        if self.step == 'class':
            return [(c, '/'.join(SHORT[k] for k in c)) for c in C.combos_for(self.race)]
        if self.step == 'alignment':
            return [(a, C.ALIGNMENTS[a]) for a in C.alignments_for(self.combo, self.race)]
        if self.step == 'god':
            return [(g, magic.GODS[g]) for g in C.gods_for(self.alignment, self.race)]
        return []

    def advance(self, value):
        if self.step == 'race':
            self.race, self.step = value, 'class'
            self.icon['size'] = 1 if value in (3, 4, 5) else 2
        elif self.step == 'class':
            self.combo, self.step = value, 'alignment'
        elif self.step == 'alignment':
            self.alignment = value
            self.step = 'god' if 'cleric' in self.combo else 'abilities'
        elif self.step == 'god':
            self.god, self.step = value, 'abilities'
        if self.step == 'abilities' and self.stats is None:
            self.reroll()
        self.sel = 0

    def back(self):
        order = [s for s in self.STEPS if s != 'god' or (self.combo and 'cleric' in self.combo)]
        i = order.index(self.step)
        if i == 0:
            if self.new_party and not self.made:
                self.message = 'A party needs at least one character.'
                return
            self.done = True
            return
        self.step, self.sel, self.message = order[i - 1], 0, None
        if self.step != 'abilities':
            self.stats = None

    def reroll(self):
        self.stats = C.roll_stats(self.rng, self.race, self.combo)

    # --- input ----------------------------------------------------------------------
    def key(self, ev):
        k, u = ev.key, ev.unicode
        if k == pygame.K_ESCAPE:
            self.back()
            return
        if self.step == 'abilities':
            if u.lower() == 'r' or k == pygame.K_SPACE:
                self.reroll()
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                short = C.qualifies(self.stats, self.combo)
                if short:
                    self.message = 'Too low for the class: %s. R rolls again.' % ', '.join(short)
                else:
                    self.step, self.message = 'name', None
            return
        if self.step == 'name':
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.finish()
            elif k == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
            elif k in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
                self.alter({pygame.K_F1: 'head', pygame.K_F2: 'body', pygame.K_F3: 'colours'}[k])
            elif u and (u.isalnum() or u in " '-") and len(self.name) < 15:
                self.name += u.upper()
            return
        if self.step == 'done':
            if u.lower() == 'n' and len(self.world.party) < MAX_PARTY:
                self.reset()
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_b):
                self.done = True
            return
        opts = self.options()
        if k in (pygame.K_UP, pygame.K_KP8):
            self.sel = (self.sel - 1) % len(opts)
        elif k in (pygame.K_DOWN, pygame.K_KP2):
            self.sel = (self.sel + 1) % len(opts)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.advance(opts[self.sel][0])

    def click(self, pos):
        i = self.row_at(pos)
        if i is not None and self.step in ('race', 'class', 'alignment', 'god'):
            self.sel = i
            self.advance(self.options()[i][0])
        elif self.step == 'abilities' and self.rect.collidepoint(pos):
            self.reroll()

    def alter(self, part):
        if part == 'head':
            self.icon['head'] = (self.icon['head'] + 1) % 9
        elif part == 'body':
            bodies = (1, 11, 14, 24, 28)
            self.icon['body'] = bodies[(bodies.index(self.icon['body']) + 1) % len(bodies)
                                       if self.icon['body'] in bodies else 0]
        else:
            self.icon['colours'] = bytes(self.rng.randint(0, 255) for _ in range(6))

    def finish(self):
        name = self.name.strip()
        if not name:
            self.message = 'Type a name first.'
            return
        if any(c.name == name for c in self.world.party):
            self.message = 'Someone in the party already has that name.'
            return
        ch = C.build(name, self.race, self.combo, self.alignment, self.stats, self.rng, self.types,
                     self.words, self.god, icon=dict(self.icon))
        if self.new_party and not self.made:
            self.world.party[:] = []
        self.world.party.append(ch)
        self.made.append(ch)
        self.world.purse['steel'] += self.rng.randint(3, 18) * (2 if 'knight' in self.combo else 10)
        self.step, self.message = 'done', None

    # --- drawing ----------------------------------------------------------------------
    def draw(self, screen):
        self.frame(screen, 'NEW PARTY' if self.new_party else self.TITLE)
        r = self.rect
        x, y = r.x + 40, r.y + 100
        chosen = [T.RACES[self.race].title() if self.race is not None else None,
                  '/'.join(SHORT[k] for k in self.combo) if self.combo else None,
                  C.ALIGNMENTS[self.alignment] if self.alignment is not None else None,
                  magic.GODS.get(self.god) if self.god else None]
        self.text(screen, '  '.join(c for c in chosen if c) or 'Choose a race.', x, y, GOOD)
        y += ROW + 16
        prompts = {'race': 'RACE', 'class': 'CLASS', 'alignment': 'ALIGNMENT', 'god': 'GOD (clerics serve one)'}
        if self.step in prompts:
            self.text(screen, prompts[self.step], x, y, HILITE)
            self.list_items(screen, [(label, '', TEXT) for _, label in self.options()], self.sel,
                            x, y + ROW, 760, r.bottom - 110)
        elif self.step in ('abilities', 'name'):
            self.text(screen, 'ABILITIES (4d6, best three)', x, y, HILITE)
            yy = y + ROW
            short = C.qualifies(self.stats, self.combo)
            for s in C.STATS:
                v = self.stats[s]
                val = '18/%02d' % (self.stats['STR18'] % 100) if s == 'STR' and self.stats.get('STR18') else str(v)
                self.text(screen, '%s  %s' % (s, val), x, yy, BAD if s in short else TEXT)
                yy += ROW
            if self.step == 'abilities':
                self.text(screen, 'R or SPACE: roll again    RETURN: keep these', x, yy + 20, DIM)
            else:
                self.text(screen, 'NAME: %s_' % self.name, x + 500, y + ROW, HILITE)
                icon = self.art._compose(self.icon)
                if icon is not None:
                    screen.blit(pygame.transform.scale(icon, (144, 144)), (x + 500, y + ROW * 3))
                self.text(screen, 'F1 head   F2 body   F3 colours   RETURN: done', x + 500, y + ROW * 8, DIM)
        elif self.step == 'done':
            ch = self.made[-1]
            names, levels = classes_text(ch)
            self.text(screen, '%s joins the party: %s %s, %d hit points.' % (ch.name, names, levels, ch.hp_max),
                      x, y, GOOD)
            self.text(screen, 'Party: ' + ', '.join(c.name for c in self.world.party), x, y + ROW, TEXT)
            more = len(self.world.party) < MAX_PARTY
            self.text(screen, ('N: make another   ' if more else '') + 'RETURN: begin', x, y + ROW * 3, HILITE)
        self.text(screen, 'ESC: back a step', r.x + 40, r.bottom - 92, DIM)
