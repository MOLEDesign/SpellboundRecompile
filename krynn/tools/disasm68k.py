#!/usr/bin/env python3
"""Annotated 68000 disassembly of the Champions of Krynn executable.

Loads the hunk file (relocated at 0x10000), then disassembles by recursive
descent from the entry point, every JSR/BSR/JMP target and every relocated
pointer that lands on a LINK A5 prologue. Everything not reached is listed
as data, with printable strings shown as text. Absolute operands that point
at strings get the string as a comment, and every routine gets its callers.

    pip install capstone
    python3 disasm68k.py game -o krynn.asm [--labels labels.txt]

labels.txt lines: ``ADDRESS name  ; optional comment`` (hex address).
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hunk import HunkFile, BASE  # noqa: E402

try:
    import capstone
except ImportError:
    sys.exit('needs capstone:  pip install capstone')

ABS_RE = re.compile(r'\$([0-9a-f]+)(?:\.l)?')
A4_RE = re.compile(r'(-?)\$([0-9a-f]+)\(a4\)')
A4LOAD_RE = re.compile(r'^\$([0-9a-f]+)\(pc\), a4$')
BRANCH = {'bra', 'jmp', 'rts', 'rte', 'rtr'}


def load_labels(path):
    labels, comments = {}, {}
    if path and os.path.exists(path):
        for line in open(path):
            line = line.split('#')[0].strip()
            if not line:
                continue
            body, _, comment = line.partition(';')
            parts = body.split()
            a = int(parts[0], 16)
            if len(parts) > 1:
                labels[a] = parts[1]
            if comment.strip():
                comments[a] = comment.strip()
    return labels, comments


class Disassembler:
    def __init__(self, hf):
        self.hf = hf
        self.img = hf.image()
        self.end = BASE + len(self.img)
        self.relocs = hf.reloc_sites()
        self.code_ranges = [(h.addr, h.addr + len(h.data)) for h in hf.hunks if h.kind == 'CODE']
        self.md = capstone.Cs(capstone.CS_ARCH_M68K,
                              capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_M68K_000)
        self.insns = {}
        self.funcs = set()
        self.xrefs = {}

    def in_code(self, a):
        return any(s <= a < e for s, e in self.code_ranges)

    def u16(self, a):
        return struct.unpack_from('>H', self.img, a - BASE)[0]

    def u32(self, a):
        return struct.unpack_from('>I', self.img, a - BASE)[0]

    # first words of routines: move.l a4,-(sp) (unit base load), link a5,
    # and the leaf routines that start by fetching arguments off the stack
    PROLOGUE = {0x2F0C, 0x4E55, 0x206F, 0x226F, 0x222F, 0x202F, 0x302F, 0x41FA, 0x2C7A, 0x48E7}
    RETURNS = {0x4E75, 0x4ED0, 0x4E73}

    def seeds(self):
        s = {BASE}
        # relocated pointers to routine prologues
        for r in self.relocs:
            t = self.u32(r)
            if self.in_code(t) and not t & 1 and self.u16(t) in self.PROLOGUE:
                s.add(t)
        # a prologue right after a return instruction starts the next routine
        for st, en in self.code_ranges:
            for a in range(st + 2, en - 4, 2):
                if self.u16(a) in (0x2F0C, 0x4E55) and self.u16(a - 2) in self.RETURNS:
                    s.add(a)
                # unit entry: link a5,#0 followed by a table of bra.w
                if self.u16(a) == 0x4E55 and self.u16(a + 4) == 0x6000:
                    b = a + 4
                    while b < en and self.u16(b) == 0x6000:
                        s.add(b)
                        b += 4
        return s

    def run(self):
        todo = list(self.seeds())
        self.funcs.update(todo)
        while todo:
            a = todo.pop()
            while self.in_code(a) and a not in self.insns:
                chunk = self.img[a - BASE:a - BASE + 10]
                ins = next(self.md.disasm(chunk, a, 1), None)
                if ins is None:
                    break
                self.insns[a] = ins
                m = ins.mnemonic
                tgt = self.target(ins)
                if tgt is not None and self.in_code(tgt):
                    self.xrefs.setdefault(tgt, set()).add(a)
                    if m in ('jsr', 'bsr', 'bsr.b', 'bsr.w', 'bsr.l'):
                        self.funcs.add(tgt)
                    if tgt not in self.insns:
                        todo.append(tgt)
                base = m.split('.')[0]
                if base in BRANCH or (base == 'jmp'):
                    break
                a += ins.size

    @staticmethod
    def target(ins):
        m = ins.mnemonic.split('.')[0]
        if m in ('jsr', 'jmp', 'bsr', 'bra') or (m.startswith('b') and m not in ('btst', 'bset', 'bclr', 'bchg')) \
                or m.startswith('db'):
            if '(' in ins.op_str:
                return None
            mm = ABS_RE.findall(ins.op_str)
            if mm:
                return int(mm[-1], 16)
        return None

    def string_at(self, a):
        if not (BASE <= a < self.end):
            return None
        s = bytearray()
        i = a - BASE
        while i < len(self.img) and 32 <= self.img[i] < 127 and len(s) < 60:
            s.append(self.img[i])
            i += 1
        if len(s) >= 4 and (i >= len(self.img) or self.img[i] == 0):
            return s.decode()
        # Pascal string: length byte
        n = self.img[a - BASE]
        if 3 <= n < 80:
            t = self.img[a - BASE + 1:a - BASE + 1 + n]
            if all(32 <= c < 127 for c in t):
                return t.decode()
        return None

    def write(self, out, labels, comments):
        names = dict(labels)
        for f in self.funcs:
            names.setdefault(f, 'sub_%06X' % f)
        for t in self.xrefs:
            names.setdefault(t, 'loc_%06X' % t)

        def sym(a):
            return names.get(a)

        for h in self.hf.hunks:
            out.write('\n;' + '=' * 70 + '\n; hunk %d  %s  %06X-%06X\n;' % (
                h.index, h.kind, h.addr, h.addr + len(h.data)) + '=' * 70 + '\n')
            a, end = h.addr, h.addr + len(h.data)
            a4 = None
            while a < end:
                if a in self.insns:
                    ins = self.insns[a]
                    # each Pascal unit keeps its globals/constants base in A4
                    m4 = A4LOAD_RE.match(ins.op_str) if ins.mnemonic == 'movea.l' else None
                    if m4:
                        a4 = self.u32(int(m4.group(1), 16))
                    if a in self.funcs or a in labels:
                        callers = sorted(self.xrefs.get(a, ()))
                        out.write('\n')
                        if a in comments:
                            out.write('; %s\n' % comments[a])
                        if callers:
                            out.write('; called from: %s\n' % ', '.join(
                                sym(c) or '%06X' % c for c in callers[:12]) + (' ...' if len(callers) > 12 else ''))
                        out.write('%s:\n' % sym(a))
                    elif a in names:
                        out.write('%s:\n' % names[a])
                    ops = ins.op_str
                    note = ''
                    for hx in ABS_RE.findall(ops):
                        v = int(hx, 16)
                        if v in names and v != a:
                            ops = ops.replace('$' + hx, names[v], 1)
                        else:
                            st = self.string_at(v)
                            if st:
                                note = '  ; "%s"' % st
                    if a4 is not None and not note:
                        for sign, off in A4_RE.findall(ins.op_str):
                            v = a4 + (-int(off, 16) if sign else int(off, 16))
                            st = self.string_at(v)
                            note = '  ; a4+%X' % (v - a4) + (' "%s"' % st if st else '') if v >= a4 else ''
                    if a in comments and a not in self.funcs:
                        note += '  ; ' + comments[a]
                    raw = self.img[a - BASE:a - BASE + ins.size].hex()
                    out.write('    %06X  %-20s %-8s %s%s\n' % (a, raw, ins.mnemonic, ops, note))
                    a += ins.size
                else:
                    b = a
                    while b < end and b not in self.insns:
                        b += 1
                    self._data(out, a, b)
                    a = b

    def _data(self, out, a, b):
        while a < b:
            st = self.string_at(a)
            if st and self.img[a - BASE] != len(st):
                n = len(st)
                out.write('    %06X  dc.b "%s",0\n' % (a, st))
                a += n + 1
                continue
            n = min(16, b - a)
            m = re.search(rb'[\x20-\x7e]{4,}\x00', self.img[a - BASE:a - BASE + n + 64])
            if m and m.start() and m.start() < n:
                n = m.start()
            out.write('    %06X  dc.b %s\n' % (a, ','.join('$%02X' % c for c in self.img[a - BASE:a - BASE + n])))
            a += n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('game')
    ap.add_argument('-o', '--out', default='krynn.asm')
    ap.add_argument('--labels', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'labels68k.txt'))
    a = ap.parse_args()
    hf = HunkFile(open(a.game, 'rb').read())
    d = Disassembler(hf)
    d.run()
    labels, comments = load_labels(a.labels)
    with open(a.out, 'w') as f:
        f.write('; Champions of Krynn (Amiga) - generated by disasm68k.py\n')
        f.write('; image base %06X, %d routines, %d instructions\n' % (BASE, len(d.funcs), len(d.insns)))
        d.write(f, labels, comments)
    code = sum(e - s for s, e in d.code_ranges)
    done = sum(i.size for i in d.insns.values())
    print('%d routines, %d instructions, %.1f%% of hunk bytes decoded as code' % (
        len(d.funcs), len(d.insns), 100.0 * done / code))


if __name__ == '__main__':
    main()
