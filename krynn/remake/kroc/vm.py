"""ECL virtual machine.

Runs the original event scripts. The VM is a generator: commands that need
the player (text, menus, pictures, combat...) yield a request tuple and the
front end sends back the answer, so the same VM drives the pygame game and
the headless test player.

Requests yielded:
    ('print', text, clear)      show text in the message area
    ('menu', items, horizontal) choose one; send back the index
    ('number',) / ('string',)   ask for input; send back the value
    ('picture', id)             show picture id (0xFF clears it)
    ('clearbox',)               clear the text area
    ('delay',)                  short pause
    ('combat', monsters)        fight; send back True if the party won
    ('treasure', args)          treasure found
    ('note', text)              something not implemented yet (logged)

Memory map (word addresses, as the original engine):
    4B00-4EFF  area/world state (flags of the module)
    7A00-7BFF  string variables
    7C00-7FFF  more state; 7C00+ also reads the selected character
    8000-9DFF  the ECL block itself (bytes)
    C04B/C04C/C04D  party X, Y, facing (0..3)
"""
import random

from cok.ecl import ECL_BASE, EclBlock

POS_X, POS_Y, POS_DIR = 0xC04B, 0xC04C, 0xC04D
IN_DUNGEON = 0x4BE6           # 0 = wilderness / overland, 1 = 3D
LAST_BLOCK = 0x4BF2           # ECL block the party came from
MAP_BLOCK = 0x4BC5            # GEO block loaded


class Halt(Exception):
    pass


class VM:
    def __init__(self, game):
        self.game = game          # front-end state: party, position, files
        self.mem = {}
        self.strings = {}
        self.block = None
        self.block_id = None
        self.flags = [False] * 6
        self.stack = []
        self.new_ecl = None
        self.rng = random.Random()
        self.entries = {}

    # --- memory ----------------------------------------------------------
    def get(self, loc):
        loc &= 0xFFFF
        if ECL_BASE <= loc <= 0x9DFF:
            return self.block.byte(loc) if self.block else 0
        if loc == POS_X:
            return self.game.x
        if loc == POS_Y:
            return self.game.y
        if loc == POS_DIR:
            return self.game.facing // 2
        if 0x7C00 <= loc <= 0x7CFF:
            v = self.game.character_value(loc - 0x7C00)
            if v is not None:
                return v
        return self.mem.get(loc, 0)

    def set(self, loc, value):
        loc &= 0xFFFF
        value &= 0xFFFF
        if ECL_BASE <= loc <= 0x9DFF:
            if self.block:
                i = loc - ECL_BASE
                if i < len(self.block.code):
                    c = bytearray(self.block.code)
                    c[i] = value & 0xFF
                    self.block.code = bytes(c)
            return
        if loc == POS_X:
            self.game.set_position(x=value)
        elif loc == POS_Y:
            self.game.set_position(y=value)
        elif loc == POS_DIR:
            self.game.set_position(facing=(value % 4) * 2)
        self.mem[loc] = value

    def get_string(self, loc):
        if loc == 0x7C00:
            return self.game.selected_name()
        if ECL_BASE <= loc <= 0x9DFF and self.block:
            s = []
            while self.block.byte(loc) and len(s) < 80:
                s.append(chr(self.block.byte(loc)))
                loc += 1
            return ''.join(s)
        return self.strings.get(loc, '')

    def set_string(self, loc, text):
        self.strings[loc] = text

    def value(self, op):
        if op.code == 0x00:
            return op.value
        if op.code in (0x01, 0x03, 0x80):
            return self.get(op.value)
        return op.value

    def text(self, op):
        if op.code == 0x80:
            return op.text
        if op.code == 0x81:
            return self.get_string(op.value)
        return str(self.value(op))

    # --- blocks ------------------------------------------------------------
    def load(self, block_id):
        self.block = EclBlock(self.game.files.ecl(block_id), block_id)
        self.block_id = block_id
        e = self.block.entries
        self.entries = {'run': e[0], 'search': e[1], 'precamp': e[2], 'campint': e[3], 'init': e[4]}
        self.stack = []
        self.flags = [False] * 6

    # --- execution -----------------------------------------------------------
    def run(self, entry):
        """Generator: run from entry point name or address until EXIT."""
        addr = self.entries[entry] if isinstance(entry, str) else entry
        self.new_ecl = None
        steps = 0
        while True:
            steps += 1
            if steps > 200000:
                yield ('note', 'script loop stopped at %04X' % addr)
                return
            ins = self.block.decode(addr)
            nxt = addr + ins.size
            handler = getattr(self, 'op_%02X' % ins.op, None)
            if handler is None:
                yield ('note', 'unknown ECL op %s at %04X' % (ins.name, addr))
                addr = nxt
                continue
            r = handler(ins)
            if hasattr(r, 'send'):          # generator: needs the front end
                r = yield from r
            if r is Halt:
                return
            if isinstance(r, int):
                addr = r
            elif r == 'skip':
                addr = nxt + self.block.decode(nxt).size
            else:
                addr = nxt
            if self.new_ecl is not None:
                return

    # --- flow ----------------------------------------------------------------
    def op_00(self, i):                       # EXIT
        return Halt

    def op_01(self, i):                       # GOTO
        return i.args[0].value

    def op_02(self, i):                       # GOSUB
        self.stack.append(i.addr + i.size)
        return i.args[0].value

    def op_13(self, i):                       # RETURN
        return self.stack.pop() if self.stack else Halt

    def _if(self, n):
        return None if self.flags[n] else 'skip'

    def op_16(self, i): return self._if(0)    # noqa: E704
    def op_17(self, i): return self._if(1)    # noqa: E704
    def op_18(self, i): return self._if(2)    # noqa: E704
    def op_19(self, i): return self._if(3)    # noqa: E704
    def op_1A(self, i): return self._if(4)    # noqa: E704
    def op_1B(self, i): return self._if(5)    # noqa: E704

    def _on(self, i, gosub):
        n = self.value(i.args[0])
        if n < len(i.args) - 2:
            if gosub:
                self.stack.append(i.addr + i.size)
            return i.args[2 + n].value
        return None

    def op_25(self, i): return self._on(i, False)   # noqa: E704  ON GOTO
    def op_26(self, i): return self._on(i, True)    # noqa: E704  ON GOSUB

    def op_20(self, i):                       # NEWECL
        self.new_ecl = self.value(i.args[0])
        return Halt

    # --- data -------------------------------------------------------------
    def _compare(self, a, b):
        self.flags = [a == b, a != b, a < b, a > b, a <= b, a >= b]

    def op_03(self, i):                       # COMPARE
        a, b = i.args
        if a.code >= 0x80 or b.code >= 0x80:
            self._compare(self.text(a), self.text(b))
        else:
            self._compare(self.value(a), self.value(b))

    def op_14(self, i):                       # COMPARE AND
        v = [self.value(a) for a in i.args]
        eq = v[0] == v[1] and v[2] == v[3]
        self.flags = [eq, not eq, False, False, False, False]

    def _arith(self, i, f):
        a, b = self.value(i.args[0]), self.value(i.args[1])
        self.set(i.args[2].value, f(a, b))

    def op_04(self, i): self._arith(i, lambda a, b: a + b)                  # noqa: E704
    def op_05(self, i): self._arith(i, lambda a, b: b - a)                  # noqa: E704
    def op_06(self, i): self._arith(i, lambda a, b: a // b if b else 0)     # noqa: E704
    def op_07(self, i): self._arith(i, lambda a, b: a * b)                  # noqa: E704

    def _logic(self, i, f):
        v = f(self.value(i.args[0]), self.value(i.args[1])) & 0xFF
        self._compare(0, v)
        self.set(i.args[2].value, v)

    def op_2F(self, i): self._logic(i, lambda a, b: a & b)   # noqa: E704 AND
    def op_30(self, i): self._logic(i, lambda a, b: a | b)   # noqa: E704 OR

    def op_08(self, i):                       # RANDOM
        top = self.value(i.args[0]) & 0xFF
        if top < 0xFF:
            top += 1
        self.set(i.args[1].value, self.rng.randrange(top) if top else 0)

    def op_09(self, i):                       # SAVE
        src, dst = i.args
        if src.code >= 0x80:
            self.set_string(dst.value, self.text(src))
        else:
            self.set(dst.value, self.value(src))

    def op_2A(self, i):                       # GETTABLE
        base = i.args[0].value
        self.set(i.args[2].value, self.get(base + (self.value(i.args[1]) & 0xFF)))

    def op_35(self, i):                       # SAVE TABLE
        self.set(i.args[1].value + self.value(i.args[2]), self.value(i.args[0]))

    # --- presentation -------------------------------------------------------
    def op_11(self, i):                       # PRINT
        yield ('print', self.text(i.args[0]), False)

    def op_12(self, i):                       # PRINTCLEAR
        yield ('print', self.text(i.args[0]), True)

    def op_33(self, i):                       # PRINT RETURN
        yield ('print', '\n', False)

    def op_3D(self, i):                       # CLEAR BOX
        yield ('clearbox',)

    def op_3A(self, i):                       # DELAY
        yield ('delay',)

    def op_0E(self, i):                       # PICTURE
        yield ('picture', self.value(i.args[0]))

    def op_31(self, i):                       # SPRITE OFF
        yield ('picture', 0xFF)

    def op_2B(self, i):                       # HORIZONTAL MENU
        items = [self.text(a) for a in i.args[2:]]
        choice = yield ('menu', items, True)
        self.set(i.args[0].value, choice or 0)

    def op_15(self, i):                       # VERTICAL MENU
        prompt = self.text(i.args[1])
        if prompt:
            yield ('print', prompt, True)
        items = [self.text(a) for a in i.args[3:]]
        choice = yield ('menu', items, False)
        self.set(i.args[0].value, choice or 0)

    def op_0F(self, i):                       # INPUT NUMBER
        v = yield ('number',)
        self.set(i.args[1].value, int(v or 0))

    def op_10(self, i):                       # INPUT STRING
        v = yield ('string',)
        self.set_string(i.args[1].value, (v or '').upper())

    # --- world ---------------------------------------------------------------
    def op_21(self, i):                       # LOAD FILES
        geo = self.value(i.args[0])
        if geo not in (0x7F, 0xFF) and self.get(IN_DUNGEON):
            self.set(MAP_BLOCK, geo)
            self.game.load_map(geo)

    def op_37(self, i):                       # LOAD PIECES (wall sets)
        a, b, c = (self.value(x) for x in i.args)
        self.game.load_walls(a, b, c)

    def op_34(self, i):                       # ECL CLOCK
        self.game.advance_clock(self.value(i.args[0]))

    def op_0A(self, i):                       # LOAD CHARACTER
        self.game.select_character(self.value(i.args[0]))

    def op_39(self, i):                       # WHO
        choice = yield ('menu', self.game.party_names(), False)
        self.game.select_character(choice or 0)

    # encounters: the remake's own combat is not written yet
    def op_1C(self, i):                       # CLEARMONSTERS
        self.game.monsters = []

    def op_0B(self, i):                       # LOAD MONSTER
        mid, count, pic = (self.value(x) for x in i.args)
        self.game.monsters.append((mid, count, pic))

    def op_0C(self, i):                       # SETUP MONSTER
        sprite, distance, pic = (self.value(x) for x in i.args)
        self.game.encounter_sprite = sprite
        yield ('sprite', sprite, distance, pic)

    def op_0D(self, i):                       # APPROACH
        yield ('approach',)

    def op_24(self, i):                       # COMBAT
        won = yield ('combat', list(self.game.monsters))
        self.game.monsters = []
        self.set(0x7EC7, 0 if won else 1)

    def op_29(self, i):                       # ENCOUNTER MENU
        """Monsters in view: COMBAT / WAIT / FLEE / ADVANCE (or PARLAY up close).

        Result written to operand 4: 0 monsters left, 1 combat, 2 party fled,
        3 talk (parlay). Operands 5-9 give the monsters' reaction to each choice,
        10-12 the texts for distance 0/1/2, 13-14 flee speeds.
        """
        sprite, max_dist, pic = (self.value(a) for a in i.args[:3])
        result = i.args[3].value
        react = [self.value(a) for a in i.args[4:9]]
        texts = [self.text(a) for a in i.args[9:12]]
        dist = min(self.game.encounter_distance(), max_dist)
        yield ('sprite', sprite, dist, pic)
        while True:
            text = texts[dist] or next((t for t in texts if t), '')
            if text:
                yield ('print', text, True)
            close = dist == 0 or not self.game.in_dungeon
            items = ['COMBAT', 'WAIT', 'FLEE', 'PARLAY' if close else 'ADVANCE']
            sel = (yield ('menu', items, True)) or 0
            if close and sel == 3:
                sel = 4
            r = react[sel]
            again = False
            if r == 0:
                self.set(result, 2 if sel == 2 else 1)
            elif r == 1:
                if sel == 0:
                    self.set(result, 1)
                elif sel == 2:
                    self.set(result, 2)
                elif sel == 4 and dist == 0:
                    self.set(result, 3)
                else:
                    if dist and sel in (3, 4):
                        dist -= 1
                        yield ('sprite', sprite, dist, pic)
                    else:
                        yield ('print', 'Both sides wait.', True)
                    again = True
            elif r == 2:
                self.set(result, 0)
                yield ('print', 'The monsters flee.', True)
            else:                               # 3/4: monsters close in
                if sel == 0:
                    self.set(result, 1)
                elif sel == 2:
                    self.set(result, 2)
                elif dist == 0 and sel in (3, 4) and r == 3 or dist == 0 and sel != 2 and r == 4:
                    self.set(result, 3)
                else:
                    if dist:
                        dist -= 1
                        yield ('sprite', sprite, dist, pic)
                    else:
                        yield ('print', 'Both sides wait.', True)
                    again = True
            if not again:
                return

    def op_2C(self, i):                       # PARLAY
        values = [self.value(a) for a in i.args[:5]]
        sel = (yield ('menu', ['HAUGHTY', 'SLY', 'NICE', 'MEEK', 'ABUSIVE'], True)) or 0
        self.set(i.args[5].value, values[sel])

    def op_38(self, i):                       # PROGRAM
        n = self.value(i.args[0])
        yield ('program', n)
        if n in (3, 9):                       # 9: camp/rest then exit; 3: party dead
            return Halt

    def op_27(self, i):                       # TREASURE
        yield ('treasure', [self.value(a) for a in i.args])

    def op_41(self, i):                       # ADD EP
        self.game.add_experience(self.value(i.args[0]), self.value(i.args[1]))

    def op_2E(self, i):                       # DAMAGE
        yield ('note', 'damage %s' % [self.value(a) for a in i.args])

    def _note(self, i):
        yield ('note', '%s %s' % (i.name, [self.value(a) if a.code < 0x80 else a.text for a in i.args]))

    # recorded but not simulated yet
    op_1D = op_1E = op_1F = op_22 = op_23 = op_28 = op_2D = op_32 = op_36 = \
        op_3B = op_3C = op_3E = op_3F = op_40 = _note
