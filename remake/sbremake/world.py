"""Room geometry, collision and Magic Knight's movement.

Coordinates are Spectrum screen pixels (256x192). The playfield is
character rows 5-23; row 23 is the floor. The original's collision map
marks only the top character row of each 16x16 block, so the row below
is filled in here to make walls and platforms solid all the way through.
"""

KNIGHT_W, KNIGHT_H = 24, 32
HIT_X0, HIT_X1 = 5, 19          # solid part of the 24-pixel-wide sprite
WALK_SPEED = 1.0                # px per 50 Hz frame (original ~0.65)
JUMP_DX = 2.0                   # horizontal speed during a jump (as original)
FALL_SPEED = 5
# vertical movement per frame of a jump, measured from the original (~55 px)
JUMP_ARC = [-7, -7, -6, -6, -5, -5, -4, -4, -3, -3, -2, -2, -1, -1, 0, 0,
            1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
SOLID_OBJECTS = {20, 25, 29, 44}   # BRICK, LUMP OF BRICKWORK x2, PLATFORM


class RoomGeometry:
    def __init__(self, rows):
        g = [[c == "#" for c in row] for row in rows]
        for y in range(5, 23, 2):          # block tops are odd rows
            for x in range(32):
                if g[y][x] and y + 1 <= 22:
                    g[y + 1][x] = True
        for y in range(5):
            g[y] = [True] * 32
        g[23] = [True] * 32
        self.base = g
        self.extra = []                     # (x, y, w, h) pixel rects
        self.removed = set()                # cells forced empty

    def cell(self, cx, cy):
        if cy < 0:
            return True
        if cy > 23:
            return True
        if cx < 0 or cx > 31:
            return False                    # room edges are exits
        if (cx, cy) in self.removed:
            return False
        return self.base[cy][cx]

    def solid_rect(self, x0, y0, x1, y1, ignore=()):
        """True if any solid cell or extra rect overlaps [x0,x1) x [y0,y1)."""
        for cy in range(int(y0) // 8, (int(y1) - 1) // 8 + 1):
            for cx in range(int(x0) // 8, (int(x1) - 1) // 8 + 1):
                if self.cell(cx, cy):
                    return True
        for r in self.extra:
            if r in ignore:
                continue
            rx, ry, rw, rh = r
            if x0 < rx + rw and x1 > rx and y0 < ry + rh and y1 > ry:
                return True
        return False


class Knight:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.facing = 0            # 0 right, 1 left
        self.anim = 0
        self.step = 0.0
        self.jump = -1             # index into JUMP_ARC, -1 when not jumping
        self.jump_dir = 0
        self.falling = False
        self.fall_dist = 0
        self.ignore = ()           # solid rects we already overlap (never get stuck in them)

    def frame(self):
        return self.anim + (4 if self.facing else 0)

    def hit(self, x=None, y=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        return (x + HIT_X0, y, x + HIT_X1, y + KNIGHT_H)

    def blocked(self, geo, x, y):
        x0, y0, x1, y1 = self.hit(x, y)
        return geo.solid_rect(x0, y0, x1, y1, self.ignore)

    def on_ground(self, geo):
        return self.blocked(geo, self.x, self.y + 1)

    def update(self, geo, left, right, jump):
        """One 50 Hz step. Returns 'left'/'right' when leaving the room."""
        x0, y0, x1, y1 = self.hit()
        self.ignore = tuple(r for r in geo.extra
                            if x0 < r[0] + r[2] and x1 > r[0] and y0 < r[1] + r[3] and y1 > r[1])
        dx = 0
        if right and not left:
            dx, self.facing = 1, 0
        elif left and not right:
            dx, self.facing = -1, 1

        grounded = self.on_ground(geo)
        if self.jump < 0 and grounded and jump:
            self.jump, self.jump_dir = 0, dx

        if self.jump >= 0:
            vx = self.jump_dir * JUMP_DX if self.jump_dir else dx * WALK_SPEED
            dy = JUMP_ARC[self.jump]
            self.jump += 1
            if self.jump >= len(JUMP_ARC):
                self.jump = -1
            self._move_x(geo, vx)
            if not self._move_y(geo, dy):
                if dy < 0:          # bumped the ceiling: start falling
                    self.jump = -1
                else:               # landed
                    self.jump = -1
        else:
            if not grounded:
                self.falling = True
                self._move_x(geo, dx * WALK_SPEED * 0.5)
                fell = self._move_y(geo, FALL_SPEED)
                self.fall_dist += FALL_SPEED if fell else 0
            else:
                self.falling = False
                self.fall_dist = 0
                if dx:
                    self._move_x(geo, dx * WALK_SPEED)
        if dx:
            self.step += abs(dx)
            if self.step >= 2:          # animation advances every 2 pixels
                self.step = 0
                self.anim = (self.anim + 1) & 3

        if self.x + HIT_X0 < 0:
            return "left"
        if self.x + HIT_X1 > 256:
            return "right"
        return None

    def _move_x(self, geo, vx):
        if not vx:
            return True
        nx = self.x + vx
        if not self.blocked(geo, nx, self.y):
            self.x = nx
            return True
        # step up small ledges (one pixel at a time) like walking up stairs
        for up in range(1, 3):
            if not self.blocked(geo, nx, self.y - up) and self.on_ground(geo):
                self.x, self.y = nx, self.y - up
                return True
        return False

    def _move_y(self, geo, dy):
        if not dy:
            return True
        step = 1 if dy > 0 else -1
        for _ in range(abs(int(dy))):
            if self.blocked(geo, self.x, self.y + step):
                return False
            self.y += step
        return True
