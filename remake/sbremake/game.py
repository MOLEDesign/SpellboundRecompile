"""Spellbound remake: game rules, rooms, characters and the command menus.

Objects, characters, rooms and all in-game text come from the baked data
pack (the original game's own data). The rules below are a reimplementation
of the quest as described by the original's texts and walkthrough, written
from scratch rather than translated from the Z80 code.
"""
import json
import os
import random

import pygame

from .assets import PAL, CYAN, WHITE, YELLOW, RED, GREEN, ink_of
from .ui import Menu, Message, PLAY, SCALE
from .world import Knight, RoomGeometry, SOLID_OBJECTS, KNIGHT_W, HIT_X0, HIT_X1

# --- object ids (index into the original object table) --------------------
SCROLL, BOOK_SHADOWS, MIOLNIR, AXE, BUN, CRYSTAL_BALL, WAND, JAVELIN = 1, 2, 3, 4, 5, 6, 7, 8
CANNON_BALL, GLUE, BROKEN_TALISMAN, MAGIC_TALISMAN, RUNESTONE, BROKEN_GLASS = 9, 10, 11, 12, 13, 14
BOOK_RUNES, GLOWING_BOTTLE, GOBLET, FUSE, RED_HERRING, BRICK = 15, 16, 17, 18, 19, 20
GREEN_CRYSTAL, BLUE_CRYSTAL, RED_CRYSTAL, ANKH, LUMP1, LIQUID_BOTTLE = 21, 22, 23, 24, 25, 26
CLOVER, ELF_BREAD, PLATFORM, GOLD_BAR, TANKARD, RING, CANDLE = 27, 28, 29, 30, 31, 32, 33
STRANGE_LIQUID, MIRROR, LASER, PRISM, ELF_HORN, MOUTH_ORGAN, TRUMPET = 34, 35, 36, 37, 38, 39, 40
INSTR_BOOK, KEY, ADVERT, LUMP2, EMPTY_BOTTLE, PLANT, SHIELD = 41, 42, 43, 44, 45, 46, 47
TELEPORT_KEY, TELEPORT_PAD = 48, 49
# --- characters -------------------------------------------------------------
GIMBAL, THOR, FLORIN, ORIK, SAMSUN, ELRAND, ROSMAR, BANSHEE = range(8)
# --- rooms --------------------------------------------------------------------
LIFT = 0
TOWER, WALL_ROOM, GALLERY_END = 9, 29, 32
GAS_ROOMS = {34, 35, 36}
TUNNEL_ENTRANCE, PIT, MOST_MAGIC = 42, 46, 48
FLOOR_NAMES_ADDR = ["DC71", "DC73", "DC75", "DC77", "DC79", "DC7B", "DC7D"]
LIFT_OK_AT_START = {0, 1, 2, 3}        # roof .. 2nd floor until Thor fixes it

READ_TEXT = {
    BOOK_SHADOWS: ["CB63", "CE6E"], RUNESTONE: ["CBA6"], CANDLE: ["CDC6"], RING: ["D383"],
    GOBLET: ["CC6C"], TANKARD: ["CC99"], LIQUID_BOTTLE: ["CD46"], FUSE: ["D09D"],
    MOUTH_ORGAN: ["D18E"], TELEPORT_PAD: ["D1ED"], GLOWING_BOTTLE: ["D240"],
    TELEPORT_KEY: ["D29E"], PLANT: ["D2C4"], AXE: ["D358"], INSTR_BOOK: ["D0E5", "D2F3"],
    ADVERT: ["CCB9"], SCROLL: ["CB36"], CRYSTAL_BALL: ["CF10"], BOOK_RUNES: ["CBE1"],
}
FOOD = {ELF_BREAD, BUN, TANKARD, GOBLET}
BLOWABLE = {ELF_HORN, TRUMPET, MOUTH_ORGAN}
WEARABLE = {SHIELD}
BREAKABLE = {MIRROR, EMPTY_BOTTLE, PRISM}
HEAVY = {PLATFORM, STRANGE_LIQUID, CANNON_BALL, GOLD_BAR}
MAX_CARRY = 5
SAVE_PATH = os.path.expanduser("~/.spellbound_remake_save.json")


class Game:
    def __init__(self, assets):
        self.a = assets
        self.g = assets.game
        self.state = "title"
        self.windows = []
        self.tick = 0
        self.geo_cache = {}
        self.music_on = True
        self.title_timer = 0
        self.new_game()
        self.show_title_menu()

    # ------------------------------------------------------------------ setup
    def new_game(self):
        self.objects = []
        for o in self.g["objects"]:
            self.objects.append({"id": o["id"], "name": o["name"], "room": o["room"],
                                 "px": o["x"] * 8, "py": (o["y"] - 1) * 8, "gfx": o["gfx"], "attr": o["attr"],
                                 "holder": None})
        self.chars = []
        for c in self.g["characters"]:
            self.chars.append({"id": c["id"], "name": c["name"], "room": c["room"], "home": c["room"],
                               "px": c["x"] * 8, "py": c["y"] * 8, "attr": c["attr"],
                               "awake": c["id"] != FLORIN, "energy": 70, "happy": 50,
                               "home_sent": False})
            for h in c["holds"]:
                self.objects[h]["holder"] = c["id"]
                self.objects[h]["room"] = None
        for i in range(len(self.chars)):
            self.chars[i]["energy"] = 60 + (i * 7) % 35
        self.chars[GIMBAL]["trapped"] = True
        s = self.g["start"]
        self.room = s["room"]
        self.knight = Knight(s["x"], s["y"])
        self.entry = (self.knight.x, self.knight.y)
        self.carried = []
        self.worn = []
        self.strength = 100
        self.flags = {"lift_floor": 2, "lift_fixed": False}
        self.ball_reads = 0
        self.read_count = {}
        self.gas_warned = False
        self.geo_cache = {}
        self.enter_room(self.room, None)

    # ---------------------------------------------------------- geometry/rooms
    def geo(self, room=None):
        room = self.room if room is None else room
        if room not in self.geo_cache:
            self.geo_cache[room] = RoomGeometry(self.g["rooms"][room]["solid"])
        geo = self.geo_cache[room]
        geo.extra = []
        for o in self.objects:
            if o["room"] == room and o["id"] in SOLID_OBJECTS and o["holder"] is None:
                geo.extra.append((o["px"], o["py"], 16, 16))
        # walls that are part of the original room layout and get demolished
        if room == WALL_ROOM and self.flags.get("wall_down"):
            geo.removed = {(x, y) for x in (14, 15) for y in range(6, 23)}
        if room == TUNNEL_ENTRANCE and self.flags.get("tunnel_open"):
            geo.removed = {(x, y) for x in (30, 31) for y in range(6, 23)}
        k = self.first_room_floor(room)
        if k is not None and k != self.flags["lift_floor"]:
            geo.extra.append((0, 144, 6, 40))          # lift door shut
        return geo

    @staticmethod
    def first_room_floor(room):
        if room >= 1 and (room - 1) % 8 == 0:
            return (room - 1) // 8
        return None

    def exits(self, room):
        left, right = self.g["rooms"][room]["exits"]
        if room == LIFT:
            return None, 1 + 8 * self.flags["lift_floor"]
        k = self.first_room_floor(room)
        if k is not None:
            left = LIFT if k == self.flags["lift_floor"] else None
        return left, right

    def enter_room(self, room, side):
        self.room = room
        kn = self.knight
        if side == "left":       # came in walking left: appear on the right
            kn.x = 256 - HIT_X1 - 1
        elif side == "right":
            kn.x = -HIT_X0 + 1
        geo = self.geo()
        # find a free spot at this x: drop down from current height, or up if inside a wall
        if kn.blocked(geo, kn.x, kn.y):
            for dy in range(0, 140):
                if not kn.blocked(geo, kn.x, kn.y - dy):
                    kn.y -= dy
                    break
                if not kn.blocked(geo, kn.x, kn.y + dy):
                    kn.y += dy
                    break
        self.entry = (kn.x, kn.y)
        self.gas_warned = False

    # -------------------------------------------------------------- helpers
    def say(self, text, obj="", who="", border=6, on_close=None, flow=True):
        if len(text) == 4 and text in self.a.text:
            text = self.a.string(text)
        self.windows.append(Message(self.a, text, obj=obj, who=who, border=border, on_close=on_close, flow=flow))

    def oname(self, i):
        return self.objects[i]["name"]

    def cname(self, c):
        return self.chars[c]["name"]

    def chars_here(self):
        return [c for c in self.chars if c["room"] == self.room]

    def objects_here(self):
        return [o for o in self.objects if o["room"] == self.room and o["holder"] is None]

    def near(self, o):
        x0, y0, x1, y1 = self.knight.hit()
        return o["px"] < x1 + 12 and o["px"] + 16 > x0 - 12 and o["py"] < y1 + 4 and o["py"] + 16 > y0 - 8

    def has(self, i):
        return i in self.carried

    def give_to_knight(self, i):
        o = self.objects[i]
        o["room"], o["holder"] = None, None
        if i not in self.carried:
            self.carried.append(i)

    def place_in_room(self, i, room, px=None, py=None):
        o = self.objects[i]
        if i in self.carried:
            self.carried.remove(i)
        if i in self.worn:
            self.worn.remove(i)
        o["holder"] = None
        o["room"] = None               # not in the room until placed (don't collide with itself)
        if px is None:
            # in front of the knight if there is room, otherwise at his feet or behind;
            # then let it fall onto whatever is below (floor, platform, another brick)
            geo = self.geo(room)
            kx = int(self.knight.x)
            front = 20 if self.knight.facing == 0 else -12
            py = int(self.knight.y)            # from head height, so bricks stack
            for off in (front, 4, -front + 8):
                px = max(0, min(240, kx + off))
                if not geo.solid_rect(px, py, px + 16, py + 16):
                    break
            while py < 168 and not geo.solid_rect(px, py + 1, px + 16, py + 17):
                py += 1
        o["px"], o["py"] = px, py
        o["room"] = room

    def char_hold(self, c, i):
        o = self.objects[i]
        if i in self.carried:
            self.carried.remove(i)
        if i in self.worn:
            self.worn.remove(i)
        o["room"], o["holder"] = None, c

    def holds(self, c):
        return [o["id"] for o in self.objects if o["holder"] == c]

    def kill(self, text):
        self.strength = 0
        self.say(text, border=2, on_close=self.game_over)

    def game_over(self):
        self.state = "dead"
        self.windows = []
        self.say("YOUR QUEST IS OVER, MAGIC KNIGHT.\n\nPRESS FIRE", border=2, on_close=self.to_title)

    def to_title(self):
        self.state = "title"
        self.windows = []
        self.show_title_menu()

    # ------------------------------------------------------------ title
    def show_title_menu(self):
        opts = [("PLAY GAME", "play"), ("INSTRUCTIONS", "help")]
        if os.path.exists(SAVE_PATH):
            opts.insert(1, ("LOAD SAVED GAME", "load"))
        opts.append(("QUIT", "quit"))
        title = "\x10\x05 SPELLBOUND\x10\x06 A TRUE\n GRAPHIC ADVENTURE\n\x10\x07   BY DAVID JONES\n   REMAKE FOR MACOS"
        self.windows = [Menu(self.a, title, opts, self.title_choice, cancel=False, border=6)]

    def title_choice(self, v):
        if v == "play":
            self.new_game()
            self.state = "play"
            self.windows = []
            self.say("C041", border=5)
        elif v == "load":
            self.load()
        elif v == "help":
            self.say("C041", border=5, on_close=lambda: self.say(
                "\x10\x05REMAKE CONTROLS\n\n\x10\x07  N OR LEFT  = WALK LEFT\n  M OR RIGHT = WALK RIGHT\n  A OR UP    = JUMP\n  SPACE = COMMAND MENU\n  ESC = CANCEL\n"
                "  F5 SAVE  F9 LOAD\n  F2 = MUSIC ON/OFF\n  F11 = FULL SCREEN", border=5, flow=False,
                on_close=self.show_title_menu))
        elif v == "quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    # -------------------------------------------------------- save / load
    def save(self):
        data = {"room": self.room, "kx": self.knight.x, "ky": self.knight.y, "objects": self.objects,
                "chars": self.chars, "carried": self.carried, "worn": self.worn, "strength": self.strength,
                "flags": self.flags, "ball_reads": self.ball_reads}
        with open(SAVE_PATH, "w") as f:
            json.dump(data, f)
        self.say("GAME SAVED", border=4)

    def load(self):
        try:
            with open(SAVE_PATH) as f:
                d = json.load(f)
        except (OSError, ValueError):
            self.say("THERE IS NO SAVED GAME", border=2)
            return
        self.new_game()
        self.objects, self.chars = d["objects"], d["chars"]
        self.carried, self.worn = d["carried"], d["worn"]
        self.strength, self.flags, self.ball_reads = d["strength"], d["flags"], d["ball_reads"]
        self.knight.x, self.knight.y = d["kx"], d["ky"]
        self.geo_cache = {}
        self.enter_room(d["room"], None)
        self.state = "play"
        self.windows = []
        self.say("GAME LOADED", border=4)

    # ------------------------------------------------------------ main loop
    def action(self, act):
        """Discrete key actions (menus, toggles)."""
        if act == "save" and self.state == "play" and not self.windows:
            self.save()
            return
        if act == "load" and not self.windows:
            self.load()
            return
        if self.windows:
            w = self.windows[-1]
            w.key(act)
            if w.done and w in self.windows:
                self.windows.remove(w)
            return
        if self.state == "play" and act == "fire":
            self.command_menu()
        elif self.state == "play" and act == "cancel":
            self.windows.append(Menu(self.a, "RETURN TO THE MAIN MENU?", [("NO", False), ("YES", True)],
                                     lambda v: v and self.to_title(), border=2))

    def update(self, keys):
        self.tick += 1
        if self.state != "play" or self.windows:
            return
        kn = self.knight
        out = kn.update(self.geo(), keys["left"], keys["right"], keys["jump"])
        if out:
            left, right = self.exits(self.room)
            dest = left if out == "left" else right
            if dest is None:
                kn.x = (-HIT_X0) if out == "left" else (256 - HIT_X1)
            else:
                self.enter_room(dest, out)
        self.hazards()
        # time passes: strength (1 point per 12 s) and the characters' energy drain slowly
        if self.tick % 600 == 0:
            self.strength -= 1
            for c in self.chars:
                if c["room"] is None:
                    continue
                if c["awake"]:
                    c["energy"] = max(0, c["energy"] - 1)
                else:
                    c["energy"] = min(100, c["energy"] + 3)
        if self.strength <= 0 and self.state == "play":
            self.kill("YOUR STRENGTH HAS RUN OUT. MAGIC KNIGHT FALLS TO THE GROUND, NEVER TO RISE AGAIN.")

    def hazards(self):
        kn = self.knight
        if self.room in GAS_ROOMS and not self.flags.get("gas_proof"):
            if self.tick % 4 == 0:
                self.strength -= 1
            if not self.gas_warned:
                self.gas_warned = True
                self.say("\x10\x04THE AIR IS FULL OF CHOKING GAS! YOUR STRENGTH IS DRAINING FAST.", border=4)
        if self.room == PIT and kn.y >= 150 and not kn.falling:
            cx = kn.x + 12
            if 96 <= cx <= 160:
                self.strength -= 25
                kn.x, kn.y = self.entry
                kn.jump = -1
                self.say("\x10\x02OUCH! YOU FELL ONTO THE SPIKES AT THE BOTTOM OF THE PIT.", border=2)

    # ---------------------------------------------------------- the commands
    def command_menu(self):
        here = self.chars_here()
        opts = [("PICK UP AN OBJECT", self.cmd_pickup), ("DROP AN OBJECT", self.cmd_drop),
                ("TAKE AN OBJECT", self.cmd_take), ("GIVE AN OBJECT", self.cmd_give),
                ("EXAMINE", self.cmd_examine)]
        readable = [i for i in self.carried if i in READ_TEXT]
        if readable:
            opts.append(("READ SOMETHING", self.cmd_read))
        if self.has(WAND) and here:
            opts.append(("COMMAND A CHARACTER", self.cmd_command))
        if self.has(CRYSTAL_BALL):
            opts.append(("LOCATE A CHARACTER", self.cmd_locate))
        if self.has(TELEPORT_KEY):
            opts.append(("TELEPORT", self.cmd_teleport))
        if self.carried:
            opts.append(("THROW SOMETHING", self.cmd_throw))
        opts.append(("CAST A SPELL", self.cmd_cast))
        if any(i in BLOWABLE for i in self.carried):
            opts.append(("BLOW SOMETHING", self.cmd_blow))
        if any(i in WEARABLE for i in self.carried) or self.worn:
            opts.append(("WEAR/UNWEAR OBJECT", self.cmd_wear))
        if self.room == LIFT:
            opts.append(("MOVE LIFT", self.cmd_move_lift))
        if self.first_room_floor(self.room) is not None:
            opts.append(("CALL LIFT", self.cmd_call_lift))
        self.windows.append(Menu(self.a, "\x10\x04COMMANDS AVAILABLE :-", opts, lambda f: f(), border=5))

    def choose_object(self, title, ids, then, empty_addr="C418"):
        if not ids:
            self.say(empty_addr)
            return
        opts = [(self.oname(i), i) for i in ids]
        if len(title) == 4 and title in self.a.text:
            title = self.a.string(title)
        self.windows.append(Menu(self.a, title, opts, then, border=5))

    def choose_char(self, chars, then, title="C44F", empty="C460", suffix=""):
        if not chars:
            self.say(empty)
            return
        t = self.a.string(title) + suffix if len(title) == 4 else title
        self.windows.append(Menu(self.a, t, [(c["name"], c["id"]) for c in chars], then, border=5))

    # pick up / drop -----------------------------------------------------------
    def cmd_pickup(self):
        here = [o for o in self.objects_here()]
        if not here:
            self.say("C61B")
            return
        near = [o["id"] for o in here if self.near(o)]
        if not near:
            self.say("C629")
            return
        if len(near) == 1:
            self.pickup(near[0])
        else:
            self.choose_object("C72F", near, self.pickup)

    def pickup(self, i):
        if i == STRANGE_LIQUID:
            self.say("C664")
        elif i in HEAVY:
            self.say("C64F", obj=self.oname(i))
        elif len(self.carried) >= MAX_CARRY:
            self.say("C63A")
        else:
            self.give_to_knight(i)
            self.say("\x10\x05YOU ARE NOW CARRYING\n\x10\x07" + "\n".join(self.oname(j) for j in self.carried), border=5, flow=False)

    def cmd_drop(self):
        self.choose_object("C695", list(self.carried), self.drop)

    def drop(self, i):
        if i == GLOWING_BOTTLE:
            if not self.flags.get("armour"):
                self.say("C6B3", obj=self.oname(i))
                return
            # the bottle shatters and releases Banshee
            self.carried.remove(i)
            self.objects[i]["room"] = None
            b = self.chars[BANSHEE]
            b["room"], b["px"], b["py"], b["home"] = self.room, int(min(220, self.knight.x + 30)), 152, self.room
            self.flags["banshee_free"] = True
            self.say("C6C4", border=4)
            return
        self.place_in_room(i, self.room)

    # take / give -------------------------------------------------------------------
    def cmd_take(self):
        self.choose_char(self.chars_here(), self.take_from, title="C475")

    def take_from(self, c):
        items = self.holds(c)
        if not items:
            self.say("C769", who=self.cname(c))
            return
        self.choose_object("C72F", items, lambda i: self.take(c, i))

    def take(self, c, i):
        ch = self.chars[c]
        if len(self.carried) >= MAX_CARRY:
            self.say("C63A")
            return
        if c == THOR and i == MIOLNIR:
            self.kill("C790")
            return
        if not ch["awake"]:
            self.give_to_knight(i)          # sleeping characters cannot object
        elif ch["happy"] < 30 or (c == GIMBAL and ch.get("trapped")):
            self.say("C77E", obj=self.oname(i), who=self.cname(c))
            return
        else:
            self.give_to_knight(i)
        if i == LIQUID_BOTTLE and c == FLORIN:
            self.strength = 100
            self.say("\x10\x05FLORIN HAS BEEN MINDING THE RESTORATIVE FLUID. YOU TAKE A SIP AND FEEL YOUR STRENGTH RETURN.", border=4)
        else:
            self.say("\x10\x05YOU TAKE THE " + self.oname(i) + " FROM " + self.cname(c), border=5)

    def cmd_give(self):
        here = self.chars_here()
        if not self.carried:
            self.say("C418")
            return
        self.choose_char(here, lambda c: self.choose_object("C812", list(self.carried), lambda i: self.give(c, i)),
                         suffix="GIVE ?")

    def give(self, c, i):
        ch = self.chars[c]
        if len(self.holds(c)) >= 4:
            self.say("C833", who=self.cname(c))
            return
        if c == GIMBAL and ch.get("trapped"):
            self.say("C85D", obj=self.oname(i), who=self.cname(c))
            return
        self.char_hold(c, i)
        ch["happy"] = min(100, ch["happy"] + 15)
        if c == THOR and i == MIOLNIR:
            self.say("\x10\x06THOR GRASPS HIS MIGHTY HAMMER MIOLNIR AND SMILES.", border=6)
        else:
            self.say("\x10\x05" + self.cname(c) + " NOW HAS THE " + self.oname(i), border=5)

    # examine ------------------------------------------------------------------------
    def cmd_examine(self):
        opts = [("OBJECT", "o"), ("CHARACTER", "c"), ("YOURSELF", "y")]
        self.windows.append(Menu(self.a, "EXAMINE WHAT ?", opts, self.examine, border=5))

    def examine(self, what):
        if what == "y":
            lines = "\x10\x05EXAMINE MAGIC KNIGHT\n\n\x10\x07STRENGTH   \x10\x04%3d\n" % self.strength
            lines += "\x10\x07CARRYING:\n" + ("\n".join(" " + self.oname(i) for i in self.carried) or " NOTHING")
            if self.worn:
                lines += "\n\x10\x07WEARING:\n" + "\n".join(" " + self.oname(i) for i in self.worn)
            extra = []
            if self.flags.get("armour"):
                extra.append("YOUR ARMOUR GLOWS")
            if self.flags.get("gas_proof"):
                extra.append("YOU ARE IMMUNE TO GAS")
            if self.flags.get("candle_lit"):
                extra.append("THE CANDLE IS LIT")
            if extra:
                lines += "\n\x10\x06" + "\n".join(extra)
            self.say(lines, border=5, flow=False)
        elif what == "c":
            self.choose_char(self.chars_here(), self.examine_char, suffix="EXAMINE ?")
        else:
            ids = list(self.carried) + [o["id"] for o in self.objects_here() if self.near(o)]
            self.choose_object("C871", ids, self.examine_obj, empty_addr="C629")

    def examine_char(self, c):
        ch = self.chars[c]
        state = "AWAKE" if ch["awake"] else "ASLEEP"
        if c == GIMBAL and ch.get("trapped"):
            state = "TRAPPED IN A WHITE-OUT SPELL"
        held = ", ".join(self.oname(i) for i in self.holds(c)) or "NOTHING"
        self.say("\x10\x05EXAMINE %s\n\n\x10\x07HAPPINESS  \x10\x04%3d\n\x10\x07STAMINA    \x10\x04%3d\n"
                 "\x10\x07%s\n\x10\x07HOLDING: \x10\x06%s" % (ch["name"], ch["happy"], ch["energy"], state, held), border=5, flow=False)

    def examine_obj(self, i):
        yn = lambda b: "YES" if b else "NO"
        self.say("\x10\x05%s\n\n\x10\x07WEIGHT    \x10\x04%s\n\x10\x07BLOW      \x10\x04%s\n\x10\x07READ      \x10\x04%s\n"
                 "\x10\x07WEAR      \x10\x04%s" % (self.oname(i), "HEAVY" if i in HEAVY else "LIGHT", yn(i in BLOWABLE),
                                                yn(i in READ_TEXT), yn(i in WEARABLE)), border=5, flow=False)

    # read --------------------------------------------------------------------------------
    def cmd_read(self):
        self.choose_object("CAFD", [i for i in self.carried if i in READ_TEXT], self.read)

    def read(self, i):
        name = self.oname(i)
        if i == SCROLL:
            if self.flags.get("candle_lit") and self.has(CANDLE):
                self.flags["scroll_read"] = True
                self.say("CD77", obj=name, border=6)
            else:
                self.say("CB36", obj=name, border=6)
            return
        if i == RUNESTONE:
            self.say("CBE1" if self.has(BOOK_RUNES) else "CBA6", obj=name, border=6)
            return
        if i == CRYSTAL_BALL:
            f = self.flags
            if not f.get("lift_fixed"):
                addr = "CF52"
            elif not f.get("wall_weakened"):
                addr = "CF7C"
            elif not f.get("wall_down"):
                addr = "CFEA"
            elif not f.get("bridge"):
                addr = "D04E"
            else:
                addr = "CF10"
            self.say(addr, obj=name, border=6)
            return
        pages = READ_TEXT[i]
        n = self.read_count.get(i, 0)
        self.read_count[i] = n + 1
        self.say(pages[n % len(pages)], obj=name, border=6)

    # commanding characters -------------------------------------------------------------
    def cmd_command(self):
        self.choose_char(self.chars_here(), self.command_char, suffix="COMMAND ?")

    def command_char(self, c):
        ch = self.chars[c]
        if ch["happy"] < 20:
            self.say("CA03", who=ch["name"])
            return
        opts = [("GO TO SLEEP", "sleep"), ("WAKE UP", "wake"), ("GO AWAY", "away"), ("HELP", "help"),
                ("EAT & DRINK", "eat"), ("BE HAPPY", "happy")]
        self.windows.append(Menu(self.a, "WHICH COMMAND DO YOU\nWANT TO USE ?", opts, lambda v: self.do_command(c, v), border=5))

    def do_command(self, c, v):
        ch, who = self.chars[c], self.chars[c]["name"]
        if c == GIMBAL and ch.get("trapped"):
            self.say("D9CB", who=who)
            return
        if v == "sleep":
            if not ch["awake"]:
                self.say("CA21", who=who)
            elif ch["energy"] > 85:
                self.say("CA2E", who=who)
            else:
                ch["awake"] = False
                self.say("CA45", who=who)
        elif v == "wake":
            if ch["awake"]:
                self.say("CA58", who=who)
            elif ch["energy"] < 10:
                self.say("CA64", who=who)
            else:
                ch["awake"] = True
                self.say("CA70", who=who)
        elif v == "away":
            if not ch["awake"] or ch["energy"] < 10:
                self.say("CA80", who=who)
            else:
                ch["room"] = ch["home"] if ch["home"] != self.room else random.choice(
                    [r for r in range(1, 57) if r not in GAS_ROOMS and r != self.room])
                self.say("CA8C", who=who)
        elif v == "eat":
            if not ch["awake"] or ch["energy"] < 5:
                self.say("CAB8", who=who)
                return
            food = [i for i in self.holds(c) if i in FOOD]
            if not food:
                self.say("CAA4", who=who)
            else:
                self.objects[food[0]]["holder"] = None
                self.objects[food[0]]["room"] = None
                ch["energy"] = min(100, ch["energy"] + 50)
                self.say("CAC9", who=who)
        elif v == "happy":
            if ch["energy"] < 10:
                self.say("CAE2", who=who)
            else:
                ch["happy"] = min(100, ch["happy"] + 30)
                self.say("CAEB", who=who)
        elif v == "help":
            if not ch["awake"] or ch["energy"] < 15:
                self.say("CA9D", who=who)
            else:
                self.help(c)

    def help(self, c):
        f, who, held = self.flags, self.cname(c), self.holds(c)
        if c == THOR and MIOLNIR in held and self.room == LIFT and not f.get("lift_fixed"):
            f["lift_fixed"] = True
            self.say("\x10\x06THOR SWINGS MIOLNIR AND GIVES THE CONTROL BOX A GOOD BASH. THE LIFT SHUDDERS... "
                     "IT CAN NOW REACH EVERY FLOOR!", border=6)
        elif c == THOR and MIOLNIR in held and self.room == TOWER and not f.get("wall_weakened"):
            f["wall_weakened"] = True
            self.say("\x10\x06THOR RAISES MIOLNIR. A BOLT OF LIGHTNING STRIKES THE TOWER AND THE WALL ON THE "
                     "SECOND FLOOR BELOW IS WEAKENED.", border=6)
        elif c == ELRAND and TRUMPET in held and self.room == WALL_ROOM and not f.get("wall_down"):
            if not f.get("wall_weakened"):
                self.say("\x10\x05ELRAND BLOWS A MIGHTY BLAST ON THE TRUMPET BUT THE WALL IS TOO STRONG. "
                         "PERHAPS SOMETHING COULD WEAKEN IT FIRST.", border=5)
                return
            f["wall_down"] = True
            self.geo_cache.pop(WALL_ROOM, None)
            for i, px in ((LUMP1, 96), (LUMP2, 136)):
                o = self.objects[i]
                o["room"], o["holder"], o["px"], o["py"] = WALL_ROOM, None, px, 168
            self.say("\x10\x06ELRAND BLOWS THE TRUMPET. THE WEAKENED WALL COMES CRASHING DOWN, LEAVING TWO "
                     "LUMPS OF BRICKWORK!", border=6)
        elif c == ROSMAR and LASER in held and self.room == TUNNEL_ENTRANCE and not f.get("tunnel_open"):
            f["tunnel_open"] = True
            self.geo_cache.pop(TUNNEL_ENTRANCE, None)
            self.say("\x10\x06ROSMAR AIMS THE POCKET LASER AT THE BRICKWORK AND CUTS A WAY INTO THE SECRET TUNNEL.", border=6)
        elif c == SAMSUN and self.room == PIT and not f.get("bridge"):
            if JAVELIN not in held:
                self.say("\x10\x05SAMSUN LOOKS AT THE PIT AND SHRUGS. HE SEEMS TO WANT SOMETHING FIRST.", border=5)
                return
            if PLATFORM not in held:
                self.say("\x10\x05SAMSUN HAS NOTHING TO THROW INTO THE PIT.", border=5)
                return
            f["bridge"] = True
            o = self.objects[PLATFORM]
            o["holder"], o["room"], o["px"], o["py"] = None, PIT, 120, 136
            self.say("\x10\x06SAMSUN HURLS HIS PLATFORM INTO THE MIDDLE OF THE PIT. NOW YOU CAN JUMP ACROSS!", border=6)
        elif c == FLORIN and BROKEN_TALISMAN in held and GLUE in held:
            for i in (BROKEN_TALISMAN, GLUE):
                self.objects[i]["holder"] = None
            self.objects[MAGIC_TALISMAN]["holder"] = FLORIN
            f["talisman"] = True
            self.say("\x10\x06FLORIN CAREFULLY GLUES THE PIECES TOGETHER. HE NOW HOLDS THE MAGIC TALISMAN.", border=6)
        else:
            self.say("\x10\x05" + who + " CANNOT HELP YOU HERE.", border=5)

    # locate / teleport ---------------------------------------------------------------------
    def cmd_locate(self):
        others = [c for c in self.chars if c["room"] is not None]
        self.choose_char(others, lambda c: self.say(
            "\x10\x05%s IS IN\n\x10\x07%s" % (self.cname(c), self.g["rooms"][self.chars[c]["room"]]["name"]), border=5,
            flow=False),
            suffix="LOCATE ?")

    def cmd_teleport(self):
        pad = self.objects[TELEPORT_PAD]
        if pad["room"] is None or pad["holder"] is not None or pad["room"] == self.room:
            self.say("DC05")
            return
        self.room = pad["room"]
        self.knight.x, self.knight.y = pad["px"] - 4, pad["py"] - 16
        self.enter_room(self.room, None)
        self.say("\x10\x05THE TELEPORT KEY GLOWS AND YOU ARE WHISKED AWAY TO THE TELEPORT PAD.", border=5)

    # throw ---------------------------------------------------------------------------------------
    def cmd_throw(self):
        here = self.chars_here()
        self.choose_object("D748", list(self.carried), lambda i: self.choose_char(
            here, lambda c: self.throw(i, c), title="C4B9"))

    def throw(self, i, c):
        who = self.cname(c)
        crystals = {BLUE_CRYSTAL: "D7C7", RED_CRYSTAL: "D83E", GREEN_CRYSTAL: "D8DC"}
        if c == GIMBAL and i in crystals:
            if not self.flags.get("crystallium"):
                self.say("D76D")
                return
            self.carried.remove(i)
            self.objects[i]["room"] = None
            hit = self.flags.setdefault("crystals_hit", [])
            hit.append(i)
            if len(hit) == 3:
                self.say(crystals[i], border=6, on_close=self.gimbal_freed)
            else:
                self.say(crystals[i], border=6)
            return
        ch = self.chars[c]
        px = ch["px"]
        if i in BREAKABLE:
            self.carried.remove(i)
            self.objects[i]["room"] = None
            if i == MIRROR:
                self.place_in_room(BROKEN_GLASS, self.room, px, 168)
            self.say("D95C", obj=self.oname(i), who=who)
        else:
            self.place_in_room(i, self.room, px, 168)
            self.say("D946", obj=self.oname(i), who=who)

    def gimbal_freed(self):
        g = self.chars[GIMBAL]
        g["trapped"] = False
        g["py"] = 152
        g["happy"] = 100
        self.flags["gimbal_free"] = True
        self.say("D481", border=6, on_close=lambda: self.say("D6C9", border=6))

    # spells ----------------------------------------------------------------------------------------
    def cmd_cast(self):
        opts = [("CRYSTALLIUM SPECTRALIS", "crys"), ("CANDELIUM ILLUMINATUS", "cand"),
                ("ARMOURIS PHOTONICUS", "armo"), ("FUMATICUS PROTECTIUM", "fuma"),
                ("PROJECT PHYSICAL BODY", "proj"), ("QUITICUS GAMUS", "quit")]
        self.windows.append(Menu(self.a, "WHICH SPELL DO YOU WANT\nTO CAST ?", opts, self.cast, border=3))

    def cast(self, s):
        f = self.flags
        if s == "quit":
            self.windows.append(Menu(self.a, "QUIT THE GAME ?", [("NO", False), ("YES", True)],
                                     lambda v: v and self.to_title(), border=2))
        elif s == "cand":
            if f.get("candle_lit"):
                self.say("D65B")
            elif not self.has(CANDLE):
                self.say("D3DA")
            elif not any(o["id"] == CLOVER for o in self.objects_here()):
                self.say("\x10\x05THE SPELL FIZZLES. YOU NEED SOME GOOD LUCK NEARBY - PERHAPS LEFT ON THE GROUND.", border=5)
            elif SHIELD not in self.worn:
                self.strength -= 40
                self.say("D415", border=2)
            else:
                f["candle_lit"] = True
                self.say("D49C", border=6)
        elif s == "armo":
            liquid = self.objects[STRANGE_LIQUID]
            on_it = (liquid["room"] == self.room and liquid["holder"] is None and
                     abs((self.knight.x + 12) - (liquid["px"] + 8)) < 14)
            if f.get("armour"):
                self.say("D66A")
            elif not on_it:
                self.say("D3DA")
            else:
                f["armour"] = True
                self.say("D4E1", border=6)
        elif s == "fuma":
            if f.get("gas_proof"):
                self.say("D680")
            elif self.has(RED_HERRING) and self.has(PLANT):
                f["gas_proof"] = True
                self.say("D58C", border=6)
            else:
                self.say("D3DA")
        elif s == "proj":
            if not (self.has(MAGIC_TALISMAN) and self.has(CRYSTAL_BALL)):
                self.say("D3DA")
                return
            others = [c for c in self.chars if c["room"] is not None and c["room"] != self.room]
            self.choose_char(others, self.project, title="D6BC")
        elif s == "crys":
            gimbal = self.chars[GIMBAL]
            orik = self.chars[ORIK]
            if f.get("gimbal_free"):
                self.say("D650")
            elif (f.get("scroll_read") and self.room == MOST_MAGIC and self.has(RING) and orik["room"] == self.room
                  and CRYSTAL_BALL in self.holds(ORIK) and BOOK_SHADOWS in self.holds(ORIK)
                  and gimbal["room"] == self.room):
                f["crystallium"] = True
                self.say("D461", border=6)
            else:
                self.say("D3DA")

    def project(self, c):
        ch = self.chars[c]
        self.say("D60A", border=6)
        self.knight.x, self.knight.y = min(220, ch["px"] + 20), ch["py"]
        self.enter_room(ch["room"], None)

    # blow / summon -------------------------------------------------------------------------------------
    def cmd_blow(self):
        self.choose_object("DA36", [i for i in self.carried if i in BLOWABLE], self.blow)

    def blow(self, i):
        if i != ELF_HORN:
            self.say("DA56", obj=self.oname(i))
            return
        cands = [c for c in self.chars if c["room"] is not None or c["id"] == BANSHEE and self.flags.get("banshee_free")]
        cands = [c for c in cands if not c.get("home_sent")]
        self.choose_char(cands, self.summon, title="WHO DO YOU WANT TO\nSUMMON ?")

    def summon(self, c):
        ch = self.chars[c]
        who = ch["name"]
        if self.flags.get("gimbal_free") and self.room == GALLERY_END:
            others = [x for x in self.chars if x["id"] != GIMBAL]
            if c == GIMBAL and not all(x.get("home_sent") for x in others):
                self.say("\x10\x05GIMBAL SHAKES HIS HEAD. \"I MUST GO LAST, MAGIC KNIGHT!\"", border=5)
                return
            if c == BANSHEE and not self.flags.get("banshee_free"):
                self.say("DA9E", who=who)
                return
            ch["home_sent"] = True
            ch["room"] = None
            if c == GIMBAL:
                self.say("DB4E", who=who, border=6, on_close=self.win)
            else:
                self.say("DB4E", who=who, border=6)
            return
        if c == GIMBAL and ch.get("trapped"):
            self.say("DA9E", who=who)
        elif ch["room"] == self.room:
            self.say("DAD7", who=who)
        elif not ch["awake"] or ch["energy"] < 10:
            self.say("DABC", who=who)
        else:
            ch["room"] = self.room
            ch["px"] = int(max(8, min(232, self.knight.x + (28 if self.knight.facing == 0 else -20))))
            ch["py"] = 152
            geo = self.geo()
            while ch["py"] > 48 and geo.solid_rect(ch["px"], ch["py"], ch["px"] + 16, ch["py"] + 32):
                ch["py"] -= 8
            self.say("DB16", who=who, border=6)

    def win(self):
        self.state = "won"
        self.windows = []
        self.say("C379", border=6, on_close=self.to_title)

    # wear ----------------------------------------------------------------------------------------------
    def cmd_wear(self):
        def wear(v):
            if v == "wear":
                cand = [i for i in self.carried if i not in self.worn]
                self.choose_object("\x10\x05WEAR WHICH OBJECT ?", cand, self.wear)
            else:
                self.choose_object("DBB3", list(self.worn), self.unwear, empty_addr="C434")
        self.windows.append(Menu(self.a, "", [("WEAR", "wear"), ("UNWEAR", "unwear")], wear, border=5))

    def wear(self, i):
        if i not in WEARABLE:
            self.say("DBE1")
        elif len(self.worn) >= 2:
            self.say("DBCA")
        else:
            self.worn.append(i)
            self.say("\x10\x05YOU ARE NOW WEARING THE " + self.oname(i), border=5)

    def unwear(self, i):
        self.worn.remove(i)
        self.say("\x10\x05YOU TAKE OFF THE " + self.oname(i), border=5)

    # lift ---------------------------------------------------------------------------------------------
    def lift_allowed(self, floor):
        return self.flags.get("lift_fixed") or floor in LIFT_OK_AT_START

    def floor_menu(self, then):
        opts = [(self.a.string(a), k) for k, a in enumerate(FLOOR_NAMES_ADDR)]
        self.windows.append(Menu(self.a, "TAKE THE LIFT TO", opts, then, border=5))

    def cmd_move_lift(self):
        def go(k):
            if not self.lift_allowed(k):
                self.say("DC7F")
            elif k == self.flags["lift_floor"]:
                self.say("DC2D")
            else:
                self.flags["lift_floor"] = k
                self.say("DC61")
        self.floor_menu(go)

    def cmd_call_lift(self):
        k = self.first_room_floor(self.room)
        if k is None:
            return
        if self.flags["lift_floor"] == k:
            self.say("DC2D")
        elif not self.lift_allowed(k):
            self.say("DC7F")
        else:
            self.flags["lift_floor"] = k
            self.say("DC61")

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        """surf is the window surface (960x720): the Spectrum-resolution world
        is scaled up into it, then all text is drawn at full resolution."""
        screen = pygame.Surface((256, 192))
        if self.state == "title":
            screen.fill((0, 0, 0))
            if self.a.loading is not None and not self.windows:
                screen.blit(self.a.loading, (0, 0))
        else:
            self.draw_room(screen)
        surf.fill((0, 0, 0))
        surf.blit(pygame.transform.scale(screen, PLAY.size), PLAY.topleft)
        if self.state != "title":
            self.draw_room_text(surf)
        if self.state in ("play", "dead", "won"):
            self.draw_hud(surf)
        for w in self.windows:
            w.draw(surf, self.tick)

    def draw_room(self, s):
        r = self.room
        s.blit(self.a.rooms[r], (0, 0))
        f = self.flags
        if r == WALL_ROOM and f.get("wall_down"):
            s.fill((0, 0, 0), (112, 48, 16, 136))
        if r == TUNNEL_ENTRANCE and f.get("tunnel_open"):
            s.fill((0, 0, 0), (240, 48, 16, 136))
        k = self.first_room_floor(r)
        if k is not None and k != f["lift_floor"]:
            s.fill(CYAN, (2, 144, 3, 40))
        if r == LIFT:
            # light the current floor on the indicator panel (R 4 3 2 1 G B)
            y = 80 + f["lift_floor"] * 8
            if (self.tick // 10) % 2:
                s.fill(YELLOW, (122, y + 1, 4, 6))
        for o in self.objects:
            if o["room"] == r and o["holder"] is None and o["gfx"] in self.a.objs:
                s.blit(self.a.tinted(self.a.objs[o["gfx"]], ink_of(o["attr"])), (o["px"], o["py"]))
        for c in self.chars:
            if c["room"] != r:
                continue
            img = self.a.tinted(self.a.chars[c["id"]], ink_of(c["attr"]))
            s.blit(img, (c["px"], c["py"]))
            if c["id"] == GIMBAL and c.get("trapped"):
                # the white-out aura
                col = PAL[15 if (self.tick // 4) % 2 else 7]
                pygame.draw.rect(s, col, (c["px"] - 4, c["py"] - 4, 24, 40), 1)
                aura = self.flags.get("crystals_hit", [])
                for n, cr in enumerate((RED_CRYSTAL, GREEN_CRYSTAL, BLUE_CRYSTAL)):
                    if cr not in aura:
                        pygame.draw.rect(s, (RED, GREEN, PAL[9])[n], (c["px"] - 6 - n * 2, c["py"] - 6 - n * 2,
                                                                       28 + n * 4, 44 + n * 4), 1)
        kn = self.knight
        col = YELLOW if self.flags.get("armour") and (self.tick // 6) % 2 else CYAN
        s.blit(self.a.tinted(self.a.knight[kn.frame()], col), (int(kn.x), int(kn.y)))

    def draw_room_text(self, surf):
        t = self.a.type
        # room name on the ceiling row (row 5), like the original, on a black band
        name = self.g["rooms"][self.room]["name"]
        size = 24
        w = t.width(name, size) + 40
        y = PLAY.top + 40 * SCALE
        surf.fill((0, 0, 0), (PLAY.centerx - w // 2, y - 2, w, 8 * SCALE + 4))
        t.draw(surf, PLAY.centerx, y + 1, name, WHITE, size, center=True)
        # sleeping characters
        if (self.tick // 25) % 2:
            for c in self.chars_here():
                if not c["awake"]:
                    t.draw(surf, PLAY.left + (c["px"] + 14) * SCALE, PLAY.top + (c["py"] - 10) * SCALE,
                           "Zz", WHITE, 22)

    def draw_hud(self, surf):
        a, t = self.a, self.a.type
        # top border: lift position and music state
        floor = ["ROOF", "4TH FLOOR", "3RD FLOOR", "2ND FLOOR", "1ST FLOOR", "GROUND FLOOR", "BASEMENT"][self.flags["lift_floor"]]
        t.draw(surf, PLAY.left, 22, "LIFT: " + floor, PAL[13], 22)
        if not self.music_on:
            t.draw(surf, PLAY.right - t.width("MUSIC OFF  (F2)", 20), 24, "MUSIC OFF  (F2)", PAL[7], 20)
        # bottom border: strength bar and what you are carrying
        y = PLAY.bottom + 20
        t.draw(surf, PLAY.left, y, "STRENGTH", YELLOW, 22)
        w = max(0, min(100, self.strength))
        colour = GREEN if w > 40 else (YELLOW if w > 20 else RED)
        bx = PLAY.left + t.width("STRENGTH", 22) + 16
        surf.fill((70, 70, 70), (bx, y + 5, 204, 16))
        surf.fill(colour, (bx + 2, y + 7, int(w * 2), 12))
        x = PLAY.right - len(self.carried) * 40
        for i in self.carried:
            o = self.objects[i]
            if o["gfx"] in a.objs:
                icon = pygame.transform.scale(a.tinted(a.objs[o["gfx"]], ink_of(o["attr"])), (32, 32))
                surf.blit(icon, (x, y - 4))
            x += 40
