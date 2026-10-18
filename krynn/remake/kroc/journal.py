"""The manual's Journal Entries and Tavern Tales, inside the game.

The original prints "...and you record it in journal entry 51" and leaves
you to look it up in the printed manual. tools/journal.py reads your scanned
manual into extracted/journal/journal.json; this module loads it, spots
those references in the story text, and keeps the entries the party has
found so they can be read again from the Journal screen (J).
"""
import json
import os
import re

import pygame

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = [os.path.join(HERE, '..', '..', 'extracted', 'journal'),
          os.path.join(HERE, '..', 'journal')]
REF_RE = re.compile(r'(JOURNAL\s+ENTRY|TAVERN\s+TALE)(?:\s+NUMBER)?\s+(\d+)(?=\D|$)')
TITLES = {'journal': 'Journal Entry', 'tavern': 'Tavern Tale'}


class Journal:
    def __init__(self, path=None):
        self.dir = None
        self.data = {'journal': {}, 'tavern': {}}
        for d in ([path] if path else []) + SEARCH:
            f = os.path.join(d, 'journal.json')
            if os.path.exists(f):
                with open(f) as fh:
                    self.data = json.load(fh)
                self.dir = d
                break

    @property
    def available(self):
        return bool(self.data.get('journal'))

    def entry(self, kind, n):
        return self.data.get(kind, {}).get(str(n))

    def image_path(self, name):
        return os.path.join(self.dir, 'img', name) if self.dir else None

    @staticmethod
    def references(text):
        """[(kind, n)] mentioned in a piece of story text."""
        out = []
        for m in REF_RE.finditer(text.upper()):
            kind = 'journal' if m.group(1).startswith('J') else 'tavern'
            out.append((kind, int(m.group(2))))
        return out


class JournalView:
    """Full-screen reader. Modes: 'popup' shows one entry the story just
    mentioned; 'browse' lists everything found so far."""

    BG = (30, 26, 20)
    PAPER = (236, 224, 196)
    INK = (40, 30, 20)
    FRAME = (170, 120, 40)
    DIM = (120, 105, 80)
    HILITE = (255, 255, 85)

    def __init__(self, app, journal, found, focus=None, popup=False):
        self.app = app
        self.journal = journal
        self.found = found              # list of (kind, n) in the order found
        self.popup = popup
        self.kind = focus[0] if focus else 'journal'
        self.sel = 0
        self.scroll = 0
        self.done = False
        self.cache = {}
        if focus:
            items = self.items()
            self.sel = items.index(focus) if focus in items else 0

    def items(self):
        if self.popup:
            return [x for x in self.found if x[0] == self.kind][-1:] or []
        return sorted(x for x in self.found if x[0] == self.kind)

    # ------------------------------------------------------------ input
    def key(self, ev):
        k = ev.key
        if self.popup or k in (pygame.K_ESCAPE, pygame.K_j):
            if self.popup and k in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                self.scroll += 1
            elif self.popup and k in (pygame.K_UP, pygame.K_PAGEUP):
                self.scroll = max(0, self.scroll - 1)
            else:
                self.done = True
            return
        items = self.items()
        if k in (pygame.K_UP, pygame.K_w):
            self.sel = max(0, self.sel - 1)
            self.scroll = 0
        elif k in (pygame.K_DOWN, pygame.K_s):
            self.sel = min(len(items) - 1, self.sel + 1)
            self.scroll = 0
        elif k in (pygame.K_TAB, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d):
            self.kind = 'tavern' if self.kind == 'journal' else 'journal'
            self.sel, self.scroll = 0, 0
        elif k == pygame.K_PAGEDOWN:
            self.scroll += 1
        elif k == pygame.K_PAGEUP:
            self.scroll = max(0, self.scroll - 1)

    def click(self, pos):
        if self.popup:
            self.done = True
            return
        for r, i in getattr(self, 'rects', []):
            if r.collidepoint(pos):
                if isinstance(i, str):
                    self.kind, self.sel, self.scroll = i, 0, 0
                else:
                    self.sel, self.scroll = i, 0
                return

    # ------------------------------------------------------------ drawing
    def pictures(self, ref, e):
        """An entry's own pictures; tavern tales borrow the tavern illustrations."""
        if e.get('images'):
            return e['images']
        if ref[0] == 'tavern':
            art = (self.journal.entry('tavern', 0) or {}).get('images', [])
            return art[ref[1] % len(art):][:1] if art else []
        return []

    def wrap(self, font, text, width):
        words, out, line = text.split(' '), [], ''
        for w in words:
            t = (line + ' ' + w).strip()
            if font.size(t)[0] > width and line:
                out.append(line)
                line = w
            else:
                line = t
        if line:
            out.append(line)
        return out

    def image(self, name, max_w, max_h):
        key = (name, max_w, max_h)
        if key not in self.cache:
            path = self.journal.image_path(name)
            surf = None
            if path and os.path.exists(path):
                img = pygame.image.load(path)
                k = min(max_w / img.get_width(), max_h / img.get_height(), 2.0)
                surf = pygame.transform.smoothscale(img, (int(img.get_width() * k), int(img.get_height() * k)))
            self.cache[key] = surf
        return self.cache[key]

    def draw(self, screen):
        font, small = self.app.font, self.app.small
        W, H = screen.get_size()
        screen.fill(self.BG)
        items = self.items()
        rects = []
        if self.popup:
            page = pygame.Rect(160, 60, W - 320, H - 120)
            e0 = self.journal.entry(*items[0]) if items else None
            if e0 and not self.pictures(items[0], e0):
                n = sum(len(self.wrap(small, p, page.w - 96)) + 1 for p in e0['text'])
                page.h = max(380, min(H - 120, 220 + 36 * n))
                page.centery = H // 2
        else:
            # list of found entries on the left
            lst = pygame.Rect(40, 40, 420, H - 80)
            pygame.draw.rect(screen, (20, 18, 14), lst)
            pygame.draw.rect(screen, self.FRAME, lst, 3)
            x, y = lst.x + 20, lst.y + 16
            for kind, label in (('journal', 'JOURNAL'), ('tavern', 'TAVERN')):
                t = small.render(label, True, self.HILITE if kind == self.kind else self.DIM)
                screen.blit(t, (x, y))
                rects.append((pygame.Rect(x, y, t.get_width(), t.get_height()), kind))
                x += t.get_width() + 40
            y += 56
            if not items:
                screen.blit(small.render('nothing found yet', True, self.DIM), (lst.x + 20, y))
            first = max(0, self.sel - 18)
            for i, it in enumerate(items[first:first + 20], first):
                label = '%s %d' % (TITLES[it[0]], it[1])
                col = (0, 0, 0) if i == self.sel else (220, 210, 190)
                t = font.render(' %s ' % label, True, col, self.HILITE if i == self.sel else None)
                screen.blit(t, (lst.x + 16, y))
                rects.append((pygame.Rect(lst.x + 16, y, t.get_width(), t.get_height()), i))
                y += 46
            page = pygame.Rect(lst.right + 40, 40, W - lst.right - 80, H - 80)
            help_ = 'UP/DOWN choose   TAB journal/tavern   PGUP/PGDN scroll   J or ESC close'
            screen.blit(small.render(help_, True, self.DIM), (lst.x, H - 36))
        self.rects = rects
        pygame.draw.rect(screen, self.PAPER, page)
        pygame.draw.rect(screen, self.FRAME, page, 4)
        if not items:
            return
        kind, n = items[min(self.sel, len(items) - 1)]
        e = self.journal.entry(kind, n)
        x, y = page.x + 48, page.y + 36
        screen.blit(font.render(TITLES[kind].upper() + ' %d' % n, True, self.INK), (x, y))
        y += 70
        text_w = page.w - 96
        pics = self.pictures((kind, n), e) if e else []
        has_text = bool(e and any(p.strip() for p in e['text']))
        if pics and has_text:
            text_w = page.w // 2 - 72
        lines = []
        if e is None:
            msg = ('This entry was not found in the manual scan.' if self.journal.available else
                   'Run tools/journal.py with your scanned manual to read the journal here.')
            lines = self.wrap(small, msg, text_w)
        else:
            for para in e['text']:
                lines += self.wrap(small, para, text_w) + ['']
        per_page = (page.bottom - 60 - y) // 36
        self.scroll = min(self.scroll, max(0, len(lines) - per_page))
        for ln in lines[self.scroll:self.scroll + per_page]:
            screen.blit(small.render(ln, True, self.INK), (x, y))
            y += 36
        if len(lines) > per_page:
            more = 'PGDN / DOWN for more' if self.scroll + per_page < len(lines) else 'PGUP / UP to go back'
            screen.blit(small.render(more, True, self.DIM), (x, page.bottom - 48))
        if pics:
            px, py = (page.centerx + 24 if has_text else page.x + 48), page.y + 106
            for name in pics:
                img = self.image(name, page.right - 48 - px, (page.bottom - 48 - py) // len(pics))
                if img is not None:
                    screen.blit(img, (px, py))
                    py += img.get_height() + 16
        if self.popup:
            screen.blit(small.render('RETURN to continue - J opens the whole journal', True, self.DIM),
                        (page.x + 48, page.bottom - 48 if len(lines) <= per_page else page.bottom - 84))
