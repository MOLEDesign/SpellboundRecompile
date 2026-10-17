"""Windimation-style windows: framed text boxes and pointer menus.

Every window is modal: while one is open the game world is frozen, as in
the original. Windows are kept on a stack by the game and drawn at window
resolution (not on the 256x192 Spectrum screen), so text uses a proper
proportional font with room between the lines.
"""
import pygame

from .assets import PAL, layout_text

SCALE = 3                                   # Spectrum pixels -> window pixels
PLAY = pygame.Rect(32 * SCALE, 24 * SCALE, 256 * SCALE, 192 * SCALE)
WIN_W = 640                                 # window width in pixels
PAD = 26                                    # inner padding
TEXT_SIZE = 22


class Window:
    border = 6         # attribute ink of the frame

    def __init__(self, assets):
        self.a = assets
        self.t = assets.type
        self.done = False
        self.result = None

    # -- drawing helpers -------------------------------------------------
    def frame(self, surf, inner_h):
        """Black box with a double frame centred on the play area; returns
        the (x, y) of the text area."""
        w, h = WIN_W, inner_h + 2 * PAD
        x = PLAY.centerx - w // 2
        y = max(PLAY.top + 120, PLAY.centery - h // 2)
        y = min(y, PLAY.bottom - h - 8)
        ink = PAL[self.border + 8]
        shadow = pygame.Surface((w, h), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 120))
        surf.blit(shadow, (x + 8, y + 8))
        surf.fill((0, 0, 0), (x, y, w, h))
        pygame.draw.rect(surf, ink, (x, y, w, h), 4)
        pygame.draw.rect(surf, ink, (x + 9, y + 9, w - 18, h - 18), 2)
        return x + PAD, y + PAD

    def draw_lines(self, surf, x, y, lines, size=TEXT_SIZE):
        lh = self.t.line_height(size)
        for row, line in enumerate(lines):
            cx = x
            for text, ink in line:
                cx += self.t.draw(surf, cx, y + row * lh, text, PAL[ink + 8], size)
        return y + len(lines) * lh

    def key(self, action):
        pass

    def draw(self, surf, tick):
        pass


class Message(Window):
    """A text box closed with fire/space/enter."""

    def __init__(self, assets, text, ink=7, obj="", who="", border=6, on_close=None, flow=True):
        super().__init__(assets)
        self.lines = layout_text(self.t, text, WIN_W - 2 * PAD, TEXT_SIZE, ink, obj, who, flow=flow)[:14]
        self.border = border
        self.on_close = on_close

    def key(self, action):
        if action in ("fire", "cancel"):
            self.done = True
            if self.on_close:
                self.on_close()

    def draw(self, surf, tick):
        lh = self.t.line_height(TEXT_SIZE)
        x, y = self.frame(surf, max(1, len(self.lines)) * lh - (lh - self.t.font(TEXT_SIZE).get_height()))
        self.draw_lines(surf, x, y, self.lines)


class Menu(Window):
    """Title lines plus selectable options; a pointing finger marks the
    current option and the line is highlighted, like the original."""

    def __init__(self, assets, title, options, on_choose, ink=7, border=5, title_ink=5, cancel=True):
        super().__init__(assets)
        self.title = layout_text(self.t, title, WIN_W - 2 * PAD, TEXT_SIZE, title_ink) if title else []
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
        lh = self.t.line_height(TEXT_SIZE)
        gap = lh // 2 if self.title else 0
        x, y = self.frame(surf, len(self.title) * lh + gap + len(self.options) * lh - 4)
        oy = self.draw_lines(surf, x, y, self.title) + gap
        fh = self.t.font(TEXT_SIZE).get_height()
        for i, (label, _) in enumerate(self.options):
            yy = oy + i * lh
            if i == self.sel:
                bar = pygame.Rect(x + 26, yy - (lh - fh) // 2, WIN_W - 2 * PAD - 26, lh)
                surf.fill(PAL[15], bar)
                self.t.draw(surf, x + 38, yy, label, PAL[0], TEXT_SIZE, shadow=False)
                # pointing finger, nudging back and forth
                nx = x + ((tick // 6) % 2) * 3
                cy = yy + fh // 2
                pygame.draw.polygon(surf, PAL[13], [(nx, cy - 8), (nx + 16, cy), (nx, cy + 8)])
            else:
                self.t.draw(surf, x + 38, yy, label, PAL[self.ink + 8], TEXT_SIZE)
