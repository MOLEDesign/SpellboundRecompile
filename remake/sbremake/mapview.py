"""Castle map (M): every room as a thumbnail of its real scenery, floors as
rows, the lift shaft on the left, and a blinking Magic Knight where you are."""
import pygame

from .assets import PAL, YELLOW, WHITE, CYAN
from .ui import Window

FLOOR_NAMES = ["ROOF", "4TH FLOOR", "3RD FLOOR", "2ND FLOOR", "1ST FLOOR", "GROUND FLOOR", "BASEMENT"]
TW, TH = 84, 50                # thumbnail size (room playfield is 256x152)
PITCH_X, PITCH_Y = 92, 70
LEFT, TOP = 128, 92            # grid origin (label column is left of it)


def room_cell(room):
    """(column, floor) of a room; the lift (room 0) is column 0."""
    if room == 0:
        return None
    return (room - 1) % 8 + 1, (room - 1) // 8


class MapView(Window):
    border = 5
    _thumbs = None

    def __init__(self, game):
        super().__init__(game.a)
        self.g = game
        if MapView._thumbs is None:
            MapView._thumbs = [pygame.transform.smoothscale(r.subsurface((0, 40, 256, 152)), (TW, TH))
                               for r in game.a.rooms]

    def key(self, action):
        if action in ("map", "cancel", "fire"):
            self.done = True

    def cell_rect(self, col, floor):
        return pygame.Rect(LEFT + col * PITCH_X, TOP + floor * PITCH_Y, TW, TH)

    def draw(self, surf, tick):
        g, t = self.g, self.t
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 8, 248))
        surf.blit(shade, (0, 0))
        t.draw(surf, surf.get_width() // 2, 22, "THE CASTLE OF KARN", YELLOW, 32, center=True)

        lift_floor = g.flags["lift_floor"]
        here = g.room
        here_floor = room_cell(here)[1] if here else lift_floor

        # lift shaft
        sx = LEFT + TW // 2
        pygame.draw.line(surf, (90, 90, 110), (sx, TOP - 6), (sx, TOP + 6 * PITCH_Y + TH + 6), 6)
        for k in range(7):
            # floor label
            colour = WHITE if k == here_floor else (150, 150, 160)
            ly = TOP + k * PITCH_Y + TH // 2 - 10
            t.draw(surf, LEFT - 12 - t.width(FLOOR_NAMES[k], 18), ly, FLOOR_NAMES[k], colour, 18)
            # rooms and the corridors between them
            for col in range(1, 9):
                room = 1 + 8 * k + col - 1
                r = self.cell_rect(col, k)
                left, right = g.exits(room)
                if right is not None and col < 8:
                    pygame.draw.line(surf, (120, 120, 140), (r.right, r.centery), (r.right + PITCH_X - TW, r.centery), 4)
                if col == 1 and k == lift_floor:
                    pygame.draw.line(surf, CYAN, (sx, r.centery), (r.left, r.centery), 4)
                surf.blit(MapView._thumbs[room], r)
                pygame.draw.rect(surf, (70, 70, 90), r.inflate(4, 4), 2)
        # the lift car on its current floor
        car = self.cell_rect(0, lift_floor)
        surf.blit(MapView._thumbs[0], car)
        pygame.draw.rect(surf, CYAN, car.inflate(4, 4), 2)

        # you are here
        if here == 0:
            r = car
        else:
            col, k = room_cell(here)
            r = self.cell_rect(col, k)
        if (tick // 8) % 2:
            pygame.draw.rect(surf, YELLOW, r.inflate(10, 10), 3)
        kn = g.knight
        iw, ih = 18, 24
        colour = YELLOW if (tick // 8) % 2 else WHITE
        icon = pygame.transform.scale(g.a.tinted(g.a.knight[kn.frame()], colour), (iw, ih))
        ix = r.left + int(max(0, min(256 - 24, kn.x)) * (TW - iw) / (256 - 24))
        iy = r.top + int(max(40, min(160, kn.y)) - 40) * (TH - ih) // 120
        surf.blit(icon, (ix, iy))
        # pointer above the room
        px, py = ix + iw // 2, r.top - 8 - (tick // 6) % 3
        pygame.draw.polygon(surf, YELLOW, [(px - 9, py - 12), (px + 9, py - 12), (px, py)])

        name = g.g["rooms"][here]["name"]
        where = "YOU ARE IN %s  -  %s" % (name, "THE LIFT" if here == 0 else FLOOR_NAMES[here_floor])
        t.draw(surf, surf.get_width() // 2, TOP + 7 * PITCH_Y + 4, where, WHITE, 22, center=True)
        t.draw(surf, surf.get_width() // 2, TOP + 7 * PITCH_Y + 40, "PRESS M OR ESC TO RETURN", PAL[5], 18, center=True)
