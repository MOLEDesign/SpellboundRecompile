"""Items, treasure, the armoury and the temple.

    ItemsView     I: each character's items: ready, give, drop, use
    TreasureView  what the party finds: who takes which item
    ShopView      the armoury: buy, sell, identify (100 steel), sell gems
    TempleView    healing for money
"""
import pygame

from cok import items as I

from .spells import SPELLS
from .world import COINS

BOX = (34, 30, 52)
FRAME = (170, 120, 40)
TEXT = (255, 255, 255)
HILITE = (255, 255, 85)
DIM = (150, 150, 170)
GOOD = (120, 220, 120)
BAD = (240, 100, 90)
ROW = 38
IDENTIFY_PRICE = 100


class Panel:
    """Shared frame, fonts and helpers."""
    popup = False
    over_game = True
    TITLE = ''

    def __init__(self, app):
        self.app = app
        self.world = app.world
        self.types = self.world.files.item_types()
        self.words = self.world.files.item_words()
        self.done = False
        self.message = None
        self.rect = pygame.Rect(0, 0, 1720, 940)
        self.rect.center = (960, 540)
        self.rows = []              # (rect, index) of clickable list rows

    @property
    def party(self):
        return [c for c in self.world.party if not c.dead]

    def name(self, it, identified=None):
        return it.title(self.words, identified, self.types)

    def frame(self, screen, title=None):
        r = self.rect
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, BOX, r)
        pygame.draw.rect(screen, FRAME, r, 4)
        screen.blit(self.app.font.render(title or self.TITLE, True, HILITE), (r.x + 40, r.y + 28))
        w = self.app.small.render('Purse: %s' % self.purse_text(), True, DIM)
        screen.blit(w, (r.right - 40 - w.get_width(), r.y + 38))
        if self.message:
            screen.blit(self.app.small.render(self.message, True, BAD), (r.x + 40, r.bottom - 52))

    def text(self, screen, s, x, y, col=TEXT):
        screen.blit(self.app.small.render(s, True, col), (x, y))

    def purse_text(self):
        p = self.world.purse
        coins = ', '.join('%d %s' % (p[c], c) for c in COINS[:5] if p[c])
        extra = ', '.join('%d %s' % (p[c], c) for c in COINS[5:] if p[c])
        worth = '%d steel' % self.world.wealth()
        return worth + (' (%s)' % coins if coins and coins != '%d steel' % p['steel'] else '') + \
            ('; ' + extra if extra else '')

    def stats(self, screen, ch, x, y):
        """A character's HP, AC, THAC0 and damage."""
        n, size, bonus = ch.weapon
        dmg = '%dd%d%s' % (n, size, ('%+d' % bonus) if bonus else '')
        for line in ('%s' % ch.name, 'HP %d/%d' % (max(ch.hp, 0), ch.hp_max), 'AC %d' % ch.ac,
                     'THAC0 %d' % ch.thac0, 'Damage %s' % dmg):
            self.text(screen, line, x, y, HILITE if line == ch.name else TEXT)
            y += ROW
        return y

    def tabs(self, screen, current, x, y, who=None):
        """The party (or `who`) as numbered tabs, the current one lit."""
        for i, c in enumerate(self.party if who is None else who):
            label = '%d %s' % (i + 1, c.name)
            self.text(screen, label, x, y, HILITE if c is current else DIM)
            x += self.app.small.size(label)[0] + 44

    def row_at(self, pos):
        for r, i in self.rows:
            if r.collidepoint(pos):
                return i
        return None

    def list_items(self, screen, entries, sel, x, y, width, bottom):
        """entries: [(left text, right text, colour)]; returns nothing, records rows."""
        self.rows = []
        top = max(0, sel - (bottom - y) // ROW + 1)
        for i, (left, right, col) in enumerate(entries):
            if i < top:
                continue
            if y > bottom - ROW:
                break
            r = pygame.Rect(x - 10, y - 4, width, ROW - 2)
            if i == sel:
                pygame.draw.rect(screen, (60, 60, 110), r)
            parts = left if isinstance(left, (list, tuple)) else [(0, left)]
            for dx, part in parts:                     # (x offset, text) columns
                self.text(screen, part, x + dx, y, HILITE if i == sel else col)
            if right:
                t = self.app.small.render(right, True, DIM)
                screen.blit(t, (x + width - 30 - t.get_width(), y))
            self.rows.append((r, i))
            y += ROW


# ---------------------------------------------------------------------- items
class ItemsView(Panel):
    TITLE = 'ITEMS'

    def __init__(self, app, who=0):
        super().__init__(app)
        self.who = min(who, len(self.party) - 1)
        self.sel = 0
        self.giving = False
        self.confirm = None

    @property
    def ch(self):
        return self.party[self.who]

    def key(self, ev):
        k, u = ev.key, ev.unicode.lower()
        its = self.ch.items
        if self.confirm:
            if u == 'y':
                self.confirm()
            self.confirm = None
            return
        if self.giving:
            self.giving = False
            if u.isdigit() and 1 <= int(u) <= len(self.party):
                self.give(self.party[int(u) - 1])
            return
        if k in (pygame.K_ESCAPE, pygame.K_i):
            self.done = True
        elif k in (pygame.K_TAB, pygame.K_RIGHT, pygame.K_KP6):
            self.who, self.sel, self.message = (self.who + 1) % len(self.party), 0, None
        elif k in (pygame.K_LEFT, pygame.K_KP4):
            self.who, self.sel, self.message = (self.who - 1) % len(self.party), 0, None
        elif k in (pygame.K_UP, pygame.K_KP8, pygame.K_w) and its:
            self.sel = (self.sel - 1) % len(its)
        elif k in (pygame.K_DOWN, pygame.K_KP2, pygame.K_s) and its:
            self.sel = (self.sel + 1) % len(its)
        elif not its:
            return
        elif u == 'r' or k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.toggle_ready()
        elif u == 'g':
            self.giving = True
            self.message = 'Give to whom? Press 1-%d.' % len(self.party)
        elif u == 'd':
            it = its[self.sel]
            if it.ready and it.cursed:
                self.message = "It's cursed: it will not come off."
                return
            self.message = 'Drop %s for good? Y / N' % self.name(it)
            self.confirm = self.drop
        elif u == 'u':
            self.use()

    def click(self, pos):
        i = self.row_at(pos)
        if i is not None:
            if i == self.sel:
                self.toggle_ready()
            self.sel = i
        elif not self.rect.collidepoint(pos):
            self.done = True

    def toggle_ready(self):
        it = self.ch.items[self.sel]
        if it.ready:
            if it.cursed:
                self.message = "It's cursed: it will not come off."
                return
            it.ready = False
        else:
            why = I.can_ready(it, self.ch.items, self.types)
            if why:
                self.message = 'Cannot ready it: %s.' % why
                return
            it.ready = True
        self.message = None
        self.ch.refresh(self.types, self.words)

    def give(self, other):
        it = self.ch.items[self.sel]
        if other is self.ch:
            return
        if it.ready and it.cursed:
            self.message = "It's cursed: it will not come off."
            return
        self.ch.items.remove(it)
        it.ready = False
        other.items.append(it)
        self.message = '%s now carries %s.' % (other.name, self.name(it))
        self.sel = max(0, min(self.sel, len(self.ch.items) - 1))
        self.ch.refresh(self.types, self.words)

    def drop(self):
        it = self.ch.items.pop(self.sel)
        self.message = '%s dropped.' % self.name(it)
        self.sel = max(0, min(self.sel, len(self.ch.items) - 1))
        self.ch.refresh(self.types, self.words)

    def use(self):
        ch, it = self.ch, self.ch.items[self.sel]
        title = self.name(it, True)
        if 'Potion' in title and 'Healing' in title:
            n, size, plus = (3, 8, 3) if 'Extra' in title else (2, 4, 2)
            amount = sum(self.world.vm.rng.randint(1, size) for _ in range(n)) + plus
            ch.hp = min(ch.hp_max, max(ch.hp, 0) + amount)
            self.consume(it)
            self.message = '%s drinks it: +%d hit points.' % (ch.name, amount)
        elif 'MU Scroll' in title:
            self.scribe(ch, it)
        elif 'Potion' in title or 'Scroll' in title:
            self.message = 'Nothing happens here; it may help in a fight.'
        else:
            self.message = 'It cannot be used that way.'

    def scribe(self, ch, it):
        """A mage copies a scroll's spells into the grimoire."""
        from . import magic
        if not ch.levels.get('magic-user'):
            self.message = 'Only a mage can read it.'
            return
        red = len(ch.raw) > 0x5F and ch.raw[0x5F] in (2, 3)
        if ('Red' in self.name(it, True)) != red:
            self.message = 'Only a mage of the %s Robes can use it.' % ('Red' if not red else 'White')
            return
        top = max([lvl for (c, lvl) in magic.slots(ch, self.world.day)
                   if c == magic.MAGE and isinstance(lvl, int)] or [0])
        learned = []
        for sid in it.effects:
            sp = SPELLS.get(sid)
            if sp and sp.cls == magic.MAGE and sp.level <= top and sid not in ch.book:
                ch.book.append(sid)
                learned.append(sp.name)
        if learned:
            self.consume(it)
            self.message = '%s scribes %s.' % (ch.name, ', '.join(learned))
        else:
            self.message = 'Nothing on it that %s can learn yet.' % ch.name

    def consume(self, it):
        if it.quantity > 1:
            it.quantity -= 1
        else:
            self.ch.items.remove(it)
            self.sel = max(0, min(self.sel, len(self.ch.items) - 1))

    def draw(self, screen):
        self.frame(screen)
        r = self.rect
        x, y = r.x + 40, r.y + 100
        self.tabs(screen, self.ch, x, y)
        entries = []
        for it in self.ch.items:
            t = self.types.get(it.type)
            mark = 'YES' if it.ready else ('NO' if t is not None else '')
            entries.append(('%-4s %s' % (mark, self.name(it)), '%d lb' % (it.weight // 10), TEXT))
        if not entries:
            self.text(screen, '(carries nothing)', x, y + 70, DIM)
        self.list_items(screen, entries, self.sel, x, y + 70, 1100, r.bottom - 120)
        self.stats(screen, self.ch, r.x + 1220, y + 70)
        self.text(screen, 'R/RETURN ready   G give   D drop   U use   TAB next   ESC done',
                  x, r.bottom - 92, DIM)


# ---------------------------------------------------------------------- treasure
class TreasureView(Panel):
    TITLE = 'TREASURE'

    def __init__(self, app, found, items):
        super().__init__(app)
        self.found = found
        self.items = list(items)
        self.to = [0] * len(self.items)
        self.sel = 0

    def key(self, ev):
        k, u = ev.key, ev.unicode.lower()
        if k == pygame.K_ESCAPE or not self.items:
            self.done = True
        elif k in (pygame.K_UP, pygame.K_KP8, pygame.K_w):
            self.sel = (self.sel - 1) % len(self.items)
        elif k in (pygame.K_DOWN, pygame.K_KP2, pygame.K_s):
            self.sel = (self.sel + 1) % len(self.items)
        elif k in (pygame.K_RIGHT, pygame.K_TAB, pygame.K_KP6):
            self.to[self.sel] = (self.to[self.sel] + 1) % len(self.party)
        elif k in (pygame.K_LEFT, pygame.K_KP4):
            self.to[self.sel] = (self.to[self.sel] - 1) % len(self.party)
        elif u.isdigit() and 1 <= int(u) <= len(self.party):
            self.to[self.sel] = int(u) - 1
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.take(self.sel)
        elif u == 'a':
            while self.items:
                self.take(0)
            self.done = True

    def click(self, pos):
        i = self.row_at(pos)
        if i is not None:
            if i == self.sel:
                self.take(i)
            else:
                self.sel = i
        elif not self.rect.collidepoint(pos):
            self.done = True

    def take(self, i):
        it = self.items.pop(i)
        ch = self.party[self.to.pop(i)]
        it.ready = False
        ch.items.append(it)
        self.message = '%s takes %s.' % (ch.name, self.name(it))
        self.sel = max(0, min(self.sel, len(self.items) - 1))
        if not self.items:
            self.done = True

    def draw(self, screen):
        self.frame(screen)
        r = self.rect
        x, y = r.x + 40, r.y + 100
        coins = ', '.join('%d %s' % (n, c) for c, n in self.found.items())
        self.text(screen, ('The party finds ' + coins + '.') if coins else 'No coins.', x, y, GOOD)
        y += ROW + 10
        if self.items:
            entries = [(self.name(it), '-> ' + self.party[self.to[i]].name, TEXT)
                       for i, it in enumerate(self.items)]
            self.list_items(screen, entries, self.sel, x, y, 1200, r.bottom - 110)
        else:
            self.text(screen, 'No items. Press any key.', x, y, DIM)
        self.text(screen, 'arrows/1-6 choose who carries it   RETURN take   A take all   '
                  'ESC leave the rest', x, r.bottom - 92, DIM)


# ---------------------------------------------------------------------- armoury
class ShopView(Panel):
    TITLE = 'ARMOURY'

    def __init__(self, app, stock):
        super().__init__(app)
        self.stock = list(stock)
        self.mode = 'buy'
        self.who = 0
        self.sel = 0

    @property
    def ch(self):
        return self.party[self.who]

    def price(self, it):
        return max(1, it.value)

    def listing(self):
        return self.stock if self.mode == 'buy' else self.ch.items

    def key(self, ev):
        k, u = ev.key, ev.unicode.lower()
        lst = self.listing()
        if k == pygame.K_ESCAPE:
            self.done = True
        elif u == 'b':
            self.mode, self.sel = 'buy', 0
        elif u == 's':
            self.mode, self.sel = 'sell', 0
        elif u == 'j':
            self.sell_gems()
        elif k in (pygame.K_TAB, pygame.K_RIGHT, pygame.K_KP6):
            self.who, self.message = (self.who + 1) % len(self.party), None
            self.sel = 0 if self.mode == 'sell' else self.sel
        elif k in (pygame.K_LEFT, pygame.K_KP4):
            self.who, self.message = (self.who - 1) % len(self.party), None
            self.sel = 0 if self.mode == 'sell' else self.sel
        elif k in (pygame.K_UP, pygame.K_KP8) and lst:
            self.sel = (self.sel - 1) % len(lst)
        elif k in (pygame.K_DOWN, pygame.K_KP2) and lst:
            self.sel = (self.sel + 1) % len(lst)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and lst:
            self.buy() if self.mode == 'buy' else self.sell()
        elif u == 'i' and self.mode == 'sell' and lst:
            self.identify()

    def click(self, pos):
        i = self.row_at(pos)
        if i is not None:
            if i == self.sel:
                self.buy() if self.mode == 'buy' else self.sell()
            self.sel = i
        elif not self.rect.collidepoint(pos):
            self.done = True

    def buy(self):
        it = self.stock[self.sel]
        if not self.world.pay(self.price(it)):
            self.message = 'Not enough money.'
            return
        new = I.Item.from_list(it.to_list())
        new.ready = False
        self.ch.items.append(new)
        self.message = '%s buys %s.' % (self.ch.name, self.name(new))

    def sell(self):
        it = self.ch.items[self.sel]
        if it.ready and it.cursed:
            self.message = "It's cursed: it will not come off."
            return
        gain = it.value // 2
        self.ch.items.remove(it)
        self.world.purse['steel'] += gain
        self.message = 'Sold for %d steel.' % gain
        self.sel = max(0, min(self.sel, len(self.ch.items) - 1))
        self.ch.refresh(self.types, self.words)

    def identify(self):
        it = self.ch.items[self.sel]
        if not it.hidden:
            self.message = 'I can tell you nothing new about it.'
            return
        if not self.world.pay(IDENTIFY_PRICE):
            self.message = 'Identifying costs %d steel.' % IDENTIFY_PRICE
            return
        it.hidden = 0
        self.message = 'It is %s.' % self.name(it)

    def sell_gems(self):
        p, rng = self.world.purse, self.world.vm.rng
        gain = sum(rng.choice((10, 50, 100, 100, 500)) for _ in range(p['gems'])) + \
            sum(rng.randint(3, 18) * 100 for _ in range(p['jewelry']))
        if not gain:
            self.message = 'No gems or jewelry.'
            return
        p['gems'] = p['jewelry'] = 0
        p['steel'] += gain
        self.message = 'Gems and jewelry sold for %d steel.' % gain

    def draw(self, screen):
        self.frame(screen, 'ARMOURY: ' + ('BUY' if self.mode == 'buy' else 'SELL'))
        r = self.rect
        x, y = r.x + 40, r.y + 100
        self.tabs(screen, self.ch, x, y)
        y += 70
        if self.mode == 'buy':
            entries = [(self.name(it), '%d steel' % self.price(it),
                        TEXT if self.price(it) <= self.world.wealth() else DIM) for it in self.stock]
        else:
            entries = [(('YES ' if it.ready else '    ') + self.name(it), '%d steel' % (it.value // 2), TEXT)
                       for it in self.ch.items]
        if not entries:
            self.text(screen, '(nothing)', x, y, DIM)
        self.list_items(screen, entries, self.sel, x, y, 1100, r.bottom - 120)
        self.stats(screen, self.ch, r.x + 1220, y)
        self.text(screen, 'B buy  S sell  RETURN deal  I identify (%d)  J sell gems  TAB who  ESC leave'
                  % IDENTIFY_PRICE, x, r.bottom - 92, DIM)


# ---------------------------------------------------------------------- temple
class TempleView(Panel):
    TITLE = 'TEMPLE'
    PER_HP = 5

    def price(self):
        return sum(max(0, c.hp_max - max(c.hp, 0)) for c in self.party) * self.PER_HP

    def key(self, ev):
        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) or ev.unicode.lower() == 'h':
            self.heal()
        elif ev.key == pygame.K_ESCAPE:
            self.done = True

    def click(self, pos):
        if not self.rect.collidepoint(pos):
            self.done = True
        else:
            self.heal()

    def heal(self):
        cost = self.price()
        if not cost:
            self.message = 'No one here needs healing.'
            return
        if not self.world.pay(cost):
            self.message = 'The priests ask %d steel; the party has %d.' % (cost, self.world.wealth())
            return
        for c in self.party:
            c.hp = c.hp_max
        self.message = 'The priests heal the party for %d steel.' % cost

    def draw(self, screen):
        self.frame(screen)
        r = self.rect
        x, y = r.x + 40, r.y + 110
        for c in self.party:
            self.text(screen, c.name, x, y, TEXT)
            self.text(screen, '%d/%d' % (max(c.hp, 0), c.hp_max), x + 400, y,
                      GOOD if c.hp >= c.hp_max else HILITE)
            y += ROW
        y += 20
        self.text(screen, 'RETURN: heal everyone for %d steel (%d a hit point)   ESC: leave'
                  % (self.price(), self.PER_HP), x, y, DIM)
