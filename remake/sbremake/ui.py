"""Windimation-style windows: framed text boxes and pointer menus.

Every window is modal: while one is open the game world is frozen, as in
the original. Windows are kept on a stack by the game.
"""
import pygame

from .assets import PAL, format_text

WIN_COLS = 26          # text columns inside a window


class Window:
    border = 6         # attribute ink of the frame

    def __init__(self, assets):
        self.a = assets
        self.done = False
        self.result = None

    # -- drawing helpers -------------------------------------------------
    def frame(self, surf, rows, cols=WIN_COLS, top=6):
        """Draw a black box with a double frame; returns the text origin."""
        w, h = (cols + 2) * 8, (rows + 2) * 8
        x = (256 - w) // 2
        y = top * 8
        ink = PAL[self.border + 8]
        surf.fill((0, 0, 0), (x - 2, y - 2, w + 4, h + 4))
        pygame.draw.rect(surf, ink, (x, y, w, h), 2)
        pygame.draw.rect(surf, ink, (x + 4, y + 4, w - 8, h - 8), 1)
        return x + 8, y + 8

    def draw_lines(self, surf, x, y, lines):
        for row, line in enumerate(lines):
            for col, (ch, ink) in enumerate(line):
                surf.blit(self.a.glyph(ch, PAL[ink + 8]), (x + col * 8, y + row * 8))

    def key(self, action):
        pass

    def draw(self, surf, tick):
        pass


class Message(Window):
    """A text box closed with fire/space/enter."""

    def __init__(self, assets, text, ink=7, obj="", who="", border=6, on_close=None):
        super().__init__(assets)
        self.lines = format_text(text, WIN_COLS, ink, obj, who)[:16]
        self.border = border
        self.on_close = on_close

    def key(self, action):
        if action in ("fire", "cancel"):
            self.done = True
            if self.on_close:
                self.on_close()

    def draw(self, surf, tick):
        rows = max(1, len(self.lines))
        top = max(5, 14 - (rows + 2) // 2)
        x, y = self.frame(surf, rows, top=top)
        self.draw_lines(surf, x, y, self.lines)


class Menu(Window):
    """Title lines plus selectable options; a pointing finger marks the
    current option and the line is highlighted, like the original."""

    def __init__(self, assets, title, options, on_choose, ink=7, border=5, title_ink=5, cancel=True):
        super().__init__(assets)
        self.title = format_text(title, WIN_COLS, title_ink) if title else []
        self.options = options          # list of (label, value)
        self.on_choose = on_choose
        self.sel = 0
        self.ink = ink
        self.border = border
        self.can_cancel = cancel

    def key(self, action):
        if action == "up":
            self.sel = (self.sel - 1) % len(self.options)
        elif action == "down":
            self.sel = (self.sel + 1) % len(self.options)
        elif action == "fire":
            self.done = True
            self.on_choose(self.options[self.sel][1])
        elif action == "cancel" and self.can_cancel:
            self.done = True

    def draw(self, surf, tick):
        n = len(self.title) + (1 if self.title else 0) + len(self.options)
        top = max(5, 14 - (n + 2) // 2)
        x, y = self.frame(surf, n, top=top)
        self.draw_lines(surf, x, y, self.title)
        oy = y + (len(self.title) + (1 if self.title else 0)) * 8
        for i, (label, _) in enumerate(self.options):
            yy = oy + i * 8
            text = label[:WIN_COLS - 3]
            if i == self.sel:
                surf.fill(PAL[15], (x + 16, yy, (WIN_COLS - 2) * 8, 8))
                self.a.draw_text(surf, x + 24, yy, text, PAL[0])
                # pointing finger, nudging back and forth
                surf.blit(self.a.glyph(">", PAL[13]), (x + 4 + ((tick // 6) % 2), yy))
            else:
                self.a.draw_text(surf, x + 24, yy, text, PAL[self.ink + 8])
