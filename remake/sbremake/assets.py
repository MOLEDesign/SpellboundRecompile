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
        self.loading = img("loading.png").convert() if os.path.exists(os.path.join(data_dir, "img", "loading.png")) else None
        music = os.path.join(data_dir, "title.wav")
        self.music = music if os.path.exists(music) else None
        self._tint = {}
        self.type = TextRenderer()

    def tinted(self, surf, colour):
        key = (id(surf), colour)
        t = self._tint.get(key)
        if t is None:
            t = surf.copy()
            t.fill(colour + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            self._tint[key] = t
        return t

    def string(self, addr):
        return self.text.get(addr, "")


# ---------------------------------------------------------------------------
# High-resolution text: the remake draws all text at window resolution with a
# proportional TrueType font (Pixelify Sans, SIL OFL - see remake/fonts/).

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
FONT_FILE = os.path.join(FONT_DIR, "PixelifySans.ttf")


class TextRenderer:
    def __init__(self):
        pygame.font.init()
        self._fonts = {}
        self._cache = {}

    def font(self, size):
        f = self._fonts.get(size)
        if f is None:
            path = FONT_FILE if os.path.exists(FONT_FILE) else None   # None = pygame's built-in font
            f = pygame.font.Font(path, size)
            self._fonts[size] = f
        return f

    def render(self, text, colour, size):
        key = (text, colour, size)
        img = self._cache.get(key)
        if img is None:
            if len(self._cache) > 4000:
                self._cache.clear()
            img = self.font(size).render(text, True, colour)
            self._cache[key] = img
        return img

    def width(self, text, size):
        return self.font(size).size(text)[0]

    def line_height(self, size):
        """Line advance including a comfortable gap between lines."""
        return int(self.font(size).get_height() * 1.3)

    def draw(self, surf, x, y, text, colour, size, center=False, shadow=True):
        img = self.render(text, colour, size)
        if center:
            x -= img.get_width() // 2
        if shadow:
            surf.blit(self.render(text, (0, 0, 0), size), (x + 2, y + 2))
        surf.blit(img, (x, y))
        return img.get_width()


def parse_cells(s, ink=7, obj="", who=""):
    """Original game string -> list of (char, ink); '\n' marks line breaks.
    Control codes: a leading 01-0F byte is the window height (ignored),
    10 n sets the ink, 09 is an indent, 11-13 (flash/bright) are ignored,
    1D is the current object's name, 1E/1F the character's name."""
    if s and 1 <= ord(s[0]) <= 0x0F and s[0] not in "\x09\n":
        s = s[1:]
    cells = []
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
        elif c == "\n" or ord(c) >= 0x20:
            cells.append((c, ink))
        i += 1
    return cells


def reflow(cells, min_line=10):
    """The original breaks lines by hand to fit its 26-column windows. Join
    those soft breaks back into flowing text: a single newline after a long
    line becomes a space; blank lines and short lines (lists, labels) stay."""
    out, run = [], 0
    for i, (ch, k) in enumerate(cells):
        if ch == "\n":
            nxt = cells[i + 1][0] if i + 1 < len(cells) else "\n"
            prev = cells[i - 1][0] if i else "\n"
            if run >= min_line and nxt != "\n" and prev != "\n":
                out.append((" ", k))
                run += 1
                continue
            run = 0
        else:
            run += 1
        out.append((ch, k))
    return out


def layout_text(renderer, s, max_width, size, ink=7, obj="", who="", flow=False):
    """Word-wrap a game string to max_width pixels (flow=True also rejoins
    the original's hand-made line breaks). Returns lines; each line is a list
    of (text, ink) segments."""
    cells = parse_cells(s, ink, obj, who)
    if flow:
        cells = reflow(cells)
    # words: runs of non-space cells; keep explicit newlines
    tokens = []            # ("word", [(ch, ink)...]) | ("space",) | ("nl",)
    word = []
    for ch, k in cells:
        if ch == "\n" or ch == " ":
            if word:
                tokens.append(("word", word))
                word = []
            tokens.append(("nl",) if ch == "\n" else ("space",))
        else:
            word.append((ch, k))
    if word:
        tokens.append(("word", word))

    def segs(cs):
        out = []
        for ch, k in cs:
            if out and out[-1][1] == k:
                out[-1] = (out[-1][0] + ch, k)
            else:
                out.append((ch, k))
        return out

    def text_of(cs):
        return "".join(ch for ch, _ in cs)

    lines, line, pending_space = [], [], False
    for t in tokens:
        if t[0] == "nl":
            lines.append(segs(line))
            line, pending_space = [], False
        elif t[0] == "space":
            pending_space = bool(line)
        else:
            w = t[1]
            trial = line + ([(" ", w[0][1])] if pending_space else []) + w
            if line and renderer.width(text_of(trial), size) > max_width:
                lines.append(segs(line))
                line = list(w)
            else:
                line = trial
            pending_space = False
    if line:
        lines.append(segs(line))
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    return lines
