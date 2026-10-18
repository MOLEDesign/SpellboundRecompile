"""Save / load screen: ten slots, A to J."""
import pygame

from . import savegame

BOX = (36, 32, 64)
FRAME = (170, 120, 40)
TEXT = (255, 255, 255)
HILITE = (255, 255, 85)
DIM = (150, 150, 170)
BAD = (240, 100, 90)
ROW = 56


class SaveView:
    popup = False
    over_game = True        # drawn over the game, not instead of it

    def __init__(self, app, mode):
        self.app = app
        self.mode = mode                # 'save' or 'load'
        self.rows = savegame.listing()
        self.sel = 0
        if mode == 'load':
            used = [i for i, r in enumerate(self.rows) if r[1]]
            if used:
                self.sel = max(used, key=lambda i: self.rows[i][2])     # the newest save
        self.confirm = False
        self.message = None
        self.done = False
        self.rect = pygame.Rect(0, 0, 1100, 200 + ROW * len(self.rows))
        self.rect.center = (960, 540)

    # ------------------------------------------------------------ input
    def key(self, ev):
        k = ev.key
        if k == pygame.K_ESCAPE:
            self.done = True
        elif self.confirm:
            if ev.unicode.lower() == 'y' or k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.commit()
            else:
                self.confirm = False
        elif k in (pygame.K_UP, pygame.K_KP8):
            self.sel = (self.sel - 1) % len(self.rows)
        elif k in (pygame.K_DOWN, pygame.K_KP2):
            self.sel = (self.sel + 1) % len(self.rows)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.pick(self.sel)
        elif ev.unicode and ev.unicode.upper() in savegame.SLOTS:
            self.pick(savegame.SLOTS.index(ev.unicode.upper()))

    def click(self, pos):
        if not self.rect.collidepoint(pos):
            self.done = True
            return
        i = (pos[1] - self.rect.y - 110) // ROW
        if 0 <= i < len(self.rows):
            if self.confirm and i == self.sel:
                self.commit()
            else:
                self.pick(i)

    def pick(self, i):
        self.sel = i
        used = self.rows[i][1] is not None
        if self.mode == 'load' and not used:
            self.message = 'That slot is empty.'
            return
        if self.mode == 'save' and used:
            self.confirm = True         # overwriting asks first
            return
        self.commit()

    def commit(self):
        slot = self.rows[self.sel][0]
        try:
            if self.mode == 'save':
                self.app.save_game(slot)
            else:
                self.app.load_game(slot)
            self.done = True
        except (OSError, ValueError, KeyError) as e:
            self.message = 'Failed: %s' % e
            self.confirm = False

    # ------------------------------------------------------------ drawing
    def draw(self, screen):
        r = self.rect
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        screen.blit(shade, (0, 0))
        pygame.draw.rect(screen, BOX, r)
        pygame.draw.rect(screen, FRAME, r, 4)
        font, small = self.app.font, self.app.small
        title = 'SAVE THE GAME' if self.mode == 'save' else 'LOAD A GAME'
        screen.blit(font.render(title, True, HILITE), (r.x + 40, r.y + 32))
        y = r.y + 110
        for i, (slot, label, when) in enumerate(self.rows):
            if i == self.sel:
                pygame.draw.rect(screen, (60, 60, 110), (r.x + 16, y - 6, r.w - 32, ROW - 4))
            col = HILITE if i == self.sel else (TEXT if label else DIM)
            screen.blit(font.render(slot, True, col), (r.x + 40, y))
            screen.blit(small.render(label or '(empty)', True, col), (r.x + 110, y + 6))
            if when:
                t = small.render(when, True, DIM)
                screen.blit(t, (r.right - 40 - t.get_width(), y + 6))
            y += ROW
        if self.confirm:
            text, col = 'Overwrite slot %s?  Y / N' % self.rows[self.sel][0], BAD
        elif self.message:
            text, col = self.message, BAD
        else:
            text, col = 'Letter or RETURN to %s,  ESC to cancel' % self.mode, DIM
        screen.blit(small.render(text, True, col), (r.x + 40, r.bottom - 64))
