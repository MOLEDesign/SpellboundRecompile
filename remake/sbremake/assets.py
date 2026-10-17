"""Loading the baked data pack and drawing with the ZX font and palette."""
import json
import os

import pygame

PAL = [(0, 0, 0), (0, 0, 0xD7), (0xD7, 0, 0), (0xD7, 0, 0xD7), (0, 0xD7, 0), (0, 0xD7, 0xD7), (0xD7, 0xD7, 0), (0xD7, 0xD7, 0xD7),
       (0, 0, 0), (0, 0, 0xFF), (0xFF, 0, 0), (0xFF, 0, 0xFF), (0, 0xFF, 0), (0, 0xFF, 0xFF), (0xFF, 0xFF, 0), (0xFF, 0xFF, 0xFF)]
BLACK, BLUE, RED, MAGENTA, GREEN, CYAN, YELLOW, WHITE = (PAL[i + 8] for i in range(8))


def ink_of(attr):
    """Bright ink colour of a Spectrum attribute byte (black ink -> white)."""
    ink = attr & 7
    return PAL[(ink or 7) + 8]


class Assets:
    def __init__(self, data_dir):
        self.dir = data_dir
        with open(os.path.join(data_dir, "game.json")) as f:
            self.game = json.load(f)
        self.text = self.game["text"]
        img = lambda name: pygame.image.load(os.path.join(data_dir, "img", name))
        n = len(self.game["rooms"])
        self.rooms = [img("room_%02d.png" % r).convert() for r in range(n)]
        self.knight = [img("knight_%d.png" % i).convert_alpha() for i in range(8)]
        self.chars = [img("char_%d.png" % i).convert_alpha() for i in range(8)]
        self.objs = {}
        for i in range(1, 45):
            self.objs[i] = img("obj_%02d.png" % i).convert_alpha()
        font = img("font.png").convert_alpha()
        self.glyphs = [font.subsurface((c * 8, 0, 8, 8)) for c in range(128)]
        self.loading = img("loading.png").convert() if os.path.exists(os.path.join(data_dir, "img", "loading.png")) else None
        music = os.path.join(data_dir, "title.wav")
        self.music = music if os.path.exists(music) else None
        self._tint = {}

    def tinted(self, surf, colour):
        key = (id(surf), colour)
        t = self._tint.get(key)
        if t is None:
            t = surf.copy()
            t.fill(colour + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            self._tint[key] = t
        return t

    def glyph(self, ch, colour):
        c = ord(ch) if isinstance(ch, str) else ch
        if not 0 <= c < 128:
            c = ord("?")
        return self.tinted(self.glyphs[c], colour)

    def draw_text(self, surf, x, y, text, colour=WHITE, paper=None):
        if paper is not None:
            surf.fill(paper, (x, y, 8 * len(text), 8))
        for i, ch in enumerate(text):
            surf.blit(self.glyph(ch, colour), (x + 8 * i, y))

    def string(self, addr):
        return self.text.get(addr, "")


def format_text(s, width, ink=7, obj="", who=""):
    """Turn an original game string into wrapped lines of (char, ink) cells.

    Control codes: a leading 01-0F byte is the window height (ignored),
    10 n sets the ink, 09 is an indent, 11-13 toggle flash/bright (ignored),
    1D inserts the current object's name, 1E/1F the character's name.
    """
    if s and 1 <= ord(s[0]) <= 0x0F and s[0] not in "\x09\n":
        s = s[1:]
    cells = []           # flat list of (char, ink), '\n' as separator
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\x10" and i + 1 < len(s):
            ink = ord(s[i + 1]) & 7
            i += 2
            continue
        if c == "\x09":
            cells.append((" ", ink))
        elif c == "\x1d":
            cells.extend((ch, ink) for ch in obj)
        elif c in "\x1e\x1f":
            cells.extend((ch, ink) for ch in who)
        elif c == "\n":
            cells.append(("\n", ink))
        elif ord(c) >= 0x20:
            cells.append((c, ink))
        i += 1
    lines, line, word = [], [], []

    def flush_word():
        nonlocal line
        if not word:
            return
        if len(line) + len(word) > width and line:
            while line and line[-1][0] == " ":
                line.pop()
            lines.append(line)
            line = []
        while len(word) > width:
            lines.append(word[:width])
            del word[:width]
        line.extend(word)
        word.clear()

    for ch, k in cells:
        if ch == "\n":
            flush_word()
            lines.append(line)
            line = []
        elif ch == " ":
            flush_word()
            if len(line) < width:
                line.append((ch, k))
        else:
            word.append((ch, k))
    flush_word()
    if line:
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines
