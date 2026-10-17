"""ECL: the Gold Box event script bytecode (ECLn.DAX).

An ECL block is loaded at address 0x8000 of the 64K VM address space (after
skipping its 2-byte header). Every instruction is one opcode byte followed by
a fixed number of operands (some instructions read a count operand and then
that many more). Each operand starts with a type byte:

    0x00 lo         immediate byte
    0x01 lo hi      memory read (word address)
    0x02 lo hi      immediate word (also code addresses)
    0x03 lo hi      memory read (word address)
    0x80 n bytes..  packed string of n bytes (6-bit characters)
    0x81 lo hi      string read from memory at the word address
    other lo        byte

The block begins with five pseudo-instructions whose single operand is an
entry point: run address, search-location address, pre-camp check, camp
interrupted, initial entry point.
"""

ECL_BASE = 0x8000

# opcode: (name, operand count); count None = variable (see VARIABLE)
OPCODES = {
    0x00: ('EXIT', 0), 0x01: ('GOTO', 1), 0x02: ('GOSUB', 1), 0x03: ('COMPARE', 2),
    0x04: ('ADD', 3), 0x05: ('SUBTRACT', 3), 0x06: ('DIVIDE', 3), 0x07: ('MULTIPLY', 3),
    0x08: ('RANDOM', 2), 0x09: ('SAVE', 2), 0x0A: ('LOAD CHARACTER', 1),
    0x0B: ('LOAD MONSTER', 3), 0x0C: ('SETUP MONSTER', 3), 0x0D: ('APPROACH', 0),
    0x0E: ('PICTURE', 1), 0x0F: ('INPUT NUMBER', 2), 0x10: ('INPUT STRING', 2),
    0x11: ('PRINT', 1), 0x12: ('PRINTCLEAR', 1), 0x13: ('RETURN', 0),
    0x14: ('COMPARE AND', 4), 0x15: ('VERTICAL MENU', None), 0x16: ('IF =', 0),
    0x17: ('IF <>', 0), 0x18: ('IF <', 0), 0x19: ('IF >', 0), 0x1A: ('IF <=', 0),
    0x1B: ('IF >=', 0), 0x1C: ('CLEARMONSTERS', 0), 0x1D: ('PARTYSTRENGTH', 1),
    0x1E: ('CHECKPARTY', 6), 0x1F: ('OP 1F', 2), 0x20: ('NEWECL', 1),
    0x21: ('LOAD FILES', 3), 0x22: ('PARTY SURPRISE', 2), 0x23: ('SURPRISE', 4),
    0x24: ('COMBAT', 0), 0x25: ('ON GOTO', None), 0x26: ('ON GOSUB', None),
    0x27: ('TREASURE', 8), 0x28: ('ROB', 3), 0x29: ('ENCOUNTER MENU', 14),
    0x2A: ('GETTABLE', 3), 0x2B: ('HORIZONTAL MENU', None), 0x2C: ('PARLAY', 6),
    0x2D: ('CALL', 1), 0x2E: ('DAMAGE', 5), 0x2F: ('AND', 3), 0x30: ('OR', 3),
    0x31: ('SPRITE OFF', 0), 0x32: ('FIND ITEM', 1), 0x33: ('PRINT RETURN', 0),
    0x34: ('ECL CLOCK', 1), 0x35: ('SAVE TABLE', 3), 0x36: ('ADD NPC', 1),
    0x37: ('LOAD PIECES', 3), 0x38: ('PROGRAM', 1), 0x39: ('WHO', 1),
    0x3A: ('DELAY', 0), 0x3B: ('SPELL', 3), 0x3C: ('PROTECTION', 1),
    0x3D: ('CLEAR BOX', 0), 0x3E: ('DUMP', 0), 0x3F: ('FIND SPECIAL', 1),
    0x40: ('DESTROY ITEMS', 1), 0x41: ('ADD EP', 2),
}
# variable instructions: (fixed operands, index of the count operand)
VARIABLE = {0x15: (3, 2), 0x25: (2, 1), 0x26: (2, 1), 0x2B: (2, 1)}
JUMPS = {0x01, 0x02, 0x25, 0x26}
TERMINAL = {0x00, 0x01, 0x13, 0x20}


class DataRun:
    def __init__(self, addr, data):
        self.addr, self.data = addr, data

    def __repr__(self):
        rows = []
        for o in range(0, len(self.data), 16):
            rows.append('%04X: db %s' % (self.addr + o, ' '.join('%02X' % b for b in self.data[o:o + 16])))
        return '\n    '.join(rows)


def unpack_string(data):
    """6-bit packed text: 4 characters in 3 bytes; values < 0x20 are +0x40."""
    out = []
    bits = int.from_bytes(data, 'big')
    n = len(data) * 8 // 6
    bits >>= (len(data) * 8 - n * 6)
    for k in range(n - 1, -1, -1):
        c = (bits >> (6 * k)) & 0x3F
        if c:
            out.append(chr(c + 0x40 if c <= 0x1F else c))
    return ''.join(out)


class Operand:
    __slots__ = ('code', 'value', 'text')

    def __init__(self, code, value, text=None):
        self.code, self.value, self.text = code, value, text

    def __repr__(self):
        if self.code == 0x80:
            return repr(self.text)
        if self.code in (0x01, 0x03):
            return '[%04X]' % self.value
        if self.code == 0x81:
            return 'str[%04X]' % self.value
        if self.code == 0x02:
            return '%04X' % self.value
        return '%d' % self.value


class Instr:
    __slots__ = ('addr', 'op', 'name', 'args', 'size')

    def __init__(self, addr, op, name, args, size):
        self.addr, self.op, self.name, self.args, self.size = addr, op, name, args, size

    def targets(self):
        """Code addresses this instruction may jump to."""
        if self.op in (0x01, 0x02):
            return [self.args[0].value]
        if self.op in (0x25, 0x26):
            return [a.value for a in self.args[2:]]
        return []

    def __repr__(self):
        args = list(map(repr, self.args))
        if self.op in (0x01, 0x02):
            args = ['L%04X' % self.args[0].value]
        elif self.op in (0x25, 0x26):
            args = args[:2] + ['L%04X' % a.value for a in self.args[2:]]
        return '%04X: %-16s %s' % (self.addr, self.name, ', '.join(args))


class EclBlock:
    def __init__(self, data, id=None):
        self.id = id
        self.code = bytes(data[2:])
        self.entries = []
        pos = 0
        for _ in range(5):
            args, pos = self._operands(pos, 1)
            self.entries.append(args[0].value)
        self.header_end = pos

    def byte(self, addr):
        i = (addr - ECL_BASE) & 0xFFFF
        return self.code[i] if i < len(self.code) else 0

    def _operands(self, pos, count):
        """pos points at the opcode byte (or the last operand byte)."""
        args = []
        c = self.code
        for _ in range(count):
            code, low = c[pos + 1], c[pos + 2]
            pos += 2
            if code in (1, 2, 3, 0x81):
                pos += 1
                args.append(Operand(code, low | c[pos] << 8))
            elif code == 0x80:
                text = unpack_string(c[pos + 1:pos + 1 + low]) if low else ''
                pos += low
                args.append(Operand(code, low, text))
            else:
                args.append(Operand(code, low))
        return args, pos + 1

    def decode(self, addr):
        pos = (addr - ECL_BASE) & 0xFFFF
        op = self.code[pos]
        name, count = OPCODES.get(op, ('OP %02X' % op, 0))
        if op in VARIABLE:
            fixed, idx = VARIABLE[op]
            args, end = self._operands(pos, fixed)
            n = args[idx].value if args[idx].code in (0, 2) else 0
            more, end = self._operands(end - 1, n)
            args += more
        elif count:
            args, end = self._operands(pos, count)
        else:
            args, end = [], pos + 1
        return Instr(addr, op, name, args, end - pos)

    def disassemble(self):
        """Linear sweep from the end of the header; returns list of Instr."""
        out = []
        addr = ECL_BASE + self.header_end
        end = ECL_BASE + len(self.code)
        while addr < end:
            try:
                ins = self.decode(addr)
            except IndexError:
                break
            out.append(ins)
            addr += ins.size
        return out

    def trace(self):
        """Follow control flow from the entry points; returns {addr: Instr}."""
        seen = {}
        todo = [a for a in self.entries if ECL_BASE <= a < ECL_BASE + len(self.code)]
        end = ECL_BASE + len(self.code)
        while todo:
            addr = todo.pop()
            prev_if = False
            while ECL_BASE <= addr < end and addr not in seen:
                try:
                    ins = self.decode(addr)
                except IndexError:
                    break
                seen[addr] = ins
                for t in ins.targets():
                    if ECL_BASE <= t < end and t not in seen:
                        todo.append(t)
                if ins.op in TERMINAL and not prev_if:
                    break
                prev_if = 0x16 <= ins.op <= 0x1B
                addr += ins.size
        return seen

    def listing(self):
        labels = set(self.entries)
        code = self.trace()
        for i in code.values():
            labels.update(i.targets())
        instrs = []
        addr = ECL_BASE + self.header_end
        end = ECL_BASE + len(self.code)
        while addr < end:
            if addr in code:
                instrs.append(code[addr])
                addr += code[addr].size
            else:
                stop = addr
                while stop < end and stop not in code:
                    stop += 1
                instrs.append(DataRun(addr, self.code[addr - ECL_BASE:stop - ECL_BASE]))
                addr = stop
        names = ['run', 'search', 'precamp', 'campint', 'init']
        lines = ['; ECL block %s' % (('%02X' % self.id) if self.id is not None else '?')]
        for n, a in zip(names, self.entries):
            lines.append(';   %-8s %04X' % (n, a))
        for i in instrs:
            if i.addr in labels:
                lines.append('L%04X:' % i.addr)
            lines.append('    ' + repr(i))
        return '\n'.join(lines)
