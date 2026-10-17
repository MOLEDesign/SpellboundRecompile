#!/usr/bin/env python3
"""Tracing Z80 disassembler for the Spellbound memory image.

Starting from a set of entry points, follows control flow (jumps, calls,
RSTs, conditional branches) to separate code from data, then writes an
assembler-style listing with labels, cross references and DEFB data.

    python3 tools/z80dis.py extracted/ram48.bin --org 0x6680 --end 0x10000 \
        --entry 0x6803 -o disasm/spellbound.asm

Indirect jumps (JP (HL), jump tables) cannot be followed statically;
add extra --entry values (or a --labels file) as they are discovered.
"""
import argparse
import re

R = ["b", "c", "d", "e", "h", "l", "(hl)", "a"]
RP = ["bc", "de", "hl", "sp"]
RP2 = ["bc", "de", "hl", "af"]
CC = ["nz", "z", "nc", "c", "po", "pe", "p", "m"]
ALU = ["add a,", "adc a,", "sub ", "sbc a,", "and ", "xor ", "or ", "cp "]
ROT = ["rlc", "rrc", "rl", "rr", "sla", "sra", "sll", "srl"]
IM = ["0", "0", "1", "2", "0", "0", "1", "2"]
BLI = {(4, 0): "ldi", (4, 1): "cpi", (4, 2): "ini", (4, 3): "outi",
       (5, 0): "ldd", (5, 1): "cpd", (5, 2): "ind", (5, 3): "outd",
       (6, 0): "ldir", (6, 1): "cpir", (6, 2): "inir", (6, 3): "otir",
       (7, 0): "lddr", (7, 1): "cpdr", (7, 2): "indr", (7, 3): "otdr"}


class Insn:
    __slots__ = ("addr", "size", "text", "targets", "flow", "ref")

    def __init__(self, addr):
        self.addr = addr
        self.size = 0
        self.text = ""
        self.targets = []   # code targets (jump/call)
        self.flow = True    # execution continues to next instruction
        self.ref = None     # 16-bit immediate/address operand (for data xrefs)


def decode(mem, addr):
    """Decode one instruction at addr. mem is indexable (64K)."""
    ins = Insn(addr)
    pos = [addr]

    def b():
        v = mem[pos[0] & 0xFFFF]
        pos[0] += 1
        return v

    def w():
        lo = b()
        return lo | b() << 8

    def d8():
        v = b()
        return v - 256 if v > 127 else v

    idx = None
    op = b()
    while op in (0xDD, 0xFD):
        idx = "ix" if op == 0xDD else "iy"
        op = b()

    def hl():
        return idx or "hl"

    def r(n, disp=None, allow_half=True):
        if n == 6:
            if idx:
                d = disp if disp is not None else d8()
                return "(%s%+d)" % (idx, d)
            return "(hl)"
        if idx and allow_half and n in (4, 5):
            return idx + ("h" if n == 4 else "l")
        return R[n]

    def hexw(v):
        return "$%04X" % v

    def setw(v, fmt):
        ins.ref = v
        return fmt % hexw(v)

    if op == 0xCB:
        if idx:
            d = d8()
            op2 = b()
            x, y, z = op2 >> 6, (op2 >> 3) & 7, op2 & 7
            m = "(%s%+d)" % (idx, d)
            if x == 0:
                t = "%s %s" % (ROT[y], m)
            elif x == 1:
                t = "bit %d,%s" % (y, m)
            elif x == 2:
                t = "res %d,%s" % (y, m)
            else:
                t = "set %d,%s" % (y, m)
            if x != 1 and z != 6:
                t += "," + R[z]
        else:
            op2 = b()
            x, y, z = op2 >> 6, (op2 >> 3) & 7, op2 & 7
            t = [ROT[y] + " " + R[z], "bit %d,%s" % (y, R[z]),
                 "res %d,%s" % (y, R[z]), "set %d,%s" % (y, R[z])][x]
        ins.text = t
    elif op == 0xED:
        op2 = b()
        x, y, z = op2 >> 6, (op2 >> 3) & 7, op2 & 7
        p, q = y >> 1, y & 1
        t = "defb $ED,$%02X" % op2
        if x == 1:
            if z == 0:
                t = "in (c)" if y == 6 else "in %s,(c)" % R[y]
            elif z == 1:
                t = "out (c),0" if y == 6 else "out (c),%s" % R[y]
            elif z == 2:
                t = ("sbc hl,%s" if q == 0 else "adc hl,%s") % RP[p]
            elif z == 3:
                v = w()
                t = setw(v, "ld (%%s),%s" % RP[p]) if q == 0 else setw(v, "ld %s,(%%s)" % RP[p])
            elif z == 4:
                t = "neg"
            elif z == 5:
                t = "reti" if y == 1 else "retn"
                ins.flow = False
            elif z == 6:
                t = "im " + IM[y]
            else:
                t = ["ld i,a", "ld r,a", "ld a,i", "ld a,r", "rrd", "rld", "nop", "nop"][y]
        elif x == 2 and (y, z) in BLI:
            t = BLI[(y, z)]
        ins.text = t
    else:
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1
        t = "?"
        if x == 0:
            if z == 0:
                if y == 0:
                    t = "nop"
                elif y == 1:
                    t = "ex af,af'"
                else:
                    d = d8()
                    tgt = (pos[0] + d) & 0xFFFF
                    ins.targets.append(tgt)
                    if y == 2:
                        t = "djnz " + hexw(tgt)
                    elif y == 3:
                        t = "jr " + hexw(tgt)
                        ins.flow = False
                    else:
                        t = "jr %s,%s" % (CC[y - 4], hexw(tgt))
            elif z == 1:
                if q == 0:
                    v = w()
                    reg = hl() if p == 2 else RP[p]
                    t = setw(v, "ld %s,%%s" % reg)
                else:
                    t = "add %s,%s" % (hl(), hl() if p == 2 else RP[p])
            elif z == 2:
                if y == 0:
                    t = "ld (bc),a"
                elif y == 1:
                    t = "ld a,(bc)"
                elif y == 2:
                    t = "ld (de),a"
                elif y == 3:
                    t = "ld a,(de)"
                elif y == 4:
                    t = setw(w(), "ld (%%s),%s" % hl())
                elif y == 5:
                    t = setw(w(), "ld %s,(%%s)" % hl())
                elif y == 6:
                    t = setw(w(), "ld (%s),a")
                else:
                    t = setw(w(), "ld a,(%s)")
            elif z == 3:
                t = ("inc " if q == 0 else "dec ") + (hl() if p == 2 else RP[p])
            elif z == 4:
                t = "inc " + r(y)
            elif z == 5:
                t = "dec " + r(y)
            elif z == 6:
                m = r(y)
                t = "ld %s,$%02X" % (m, b())
            else:
                t = ["rlca", "rrca", "rla", "rra", "daa", "cpl", "scf", "ccf"][y]
        elif x == 1:
            if y == 6 and z == 6:
                t = "halt"
            elif y == 6:
                t = "ld %s,%s" % (r(6), R[z])
            elif z == 6:
                t = "ld %s,%s" % (R[y], r(6))
            else:
                t = "ld %s,%s" % (r(y), r(z))
        elif x == 2:
            t = ALU[y] + r(z)
        else:
            if z == 0:
                t = "ret " + CC[y]
            elif z == 1:
                if q == 0:
                    t = "pop " + (hl() if p == 2 else RP2[p])
                else:
                    if p == 0:
                        t = "ret"
                        ins.flow = False
                    elif p == 1:
                        t = "exx"
                    elif p == 2:
                        t = "jp (%s)" % hl()
                        ins.flow = False
                    else:
                        t = "ld sp,%s" % hl()
            elif z == 2:
                v = w()
                ins.targets.append(v)
                t = "jp %s,%s" % (CC[y], hexw(v))
            elif z == 3:
                if y == 0:
                    v = w()
                    ins.targets.append(v)
                    t = "jp " + hexw(v)
                    ins.flow = False
                elif y == 2:
                    t = "out ($%02X),a" % b()
                elif y == 3:
                    t = "in a,($%02X)" % b()
                elif y == 4:
                    t = "ex (sp),%s" % hl()
                elif y == 5:
                    t = "ex de,hl"
                elif y == 6:
                    t = "di"
                elif y == 7:
                    t = "ei"
            elif z == 4:
                v = w()
                ins.targets.append(v)
                t = "call %s,%s" % (CC[y], hexw(v))
            elif z == 5:
                if q == 0:
                    t = "push " + (hl() if p == 2 else RP2[p])
                else:
                    v = w()
                    ins.targets.append(v)
                    t = "call " + hexw(v)
            elif z == 6:
                t = ALU[y] + "$%02X" % b()
            else:
                ins.targets.append(y * 8)
                t = "rst $%02X" % (y * 8)
        ins.text = t
    ins.size = pos[0] - addr
    return ins


def trace(mem, entries, lo, hi):
    code = {}
    work = list(entries)
    while work:
        a = work.pop()
        while lo <= a < hi and a not in code:
            ins = decode(mem, a)
            code[a] = ins
            for t in ins.targets:
                if lo <= t < hi and t not in code:
                    work.append(t)
            if not ins.flow:
                break
            a += ins.size
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--org", type=lambda s: int(s, 0), default=0x6680)
    ap.add_argument("--end", type=lambda s: int(s, 0), default=0x10000)
    ap.add_argument("--entry", type=lambda s: int(s, 0), action="append", default=[])
    ap.add_argument("--labels", help="file of 'ADDR name [; comment]' lines")
    ap.add_argument("-o", "--output", default="-")
    a = ap.parse_args()

    data = open(a.image, "rb").read()
    mem = bytearray(65536)
    if len(data) == 65536:
        mem[:] = data
    else:
        mem[a.org:a.org + len(data)] = data

    names, comments = {}, {}
    if a.labels:
        for line in open(a.labels):
            line = line.split("#", 1)[0].rstrip()
            if not line:
                continue
            m = re.match(r"\s*(?:\$|0x)?([0-9A-Fa-f]+)\s+(\S+)\s*(?:;\s*(.*))?", line)
            if m:
                ad = int(m.group(1), 16)
                names[ad] = m.group(2)
                if m.group(3):
                    comments[ad] = m.group(3)
                if m.group(2).startswith(("sub_", "code_", "L_")) or not m.group(2).startswith(("d_", "tab_", "var_", "msg_")):
                    a.entry.append(ad)

    code = trace(mem, a.entry or [a.org], a.org, a.end)
    callers = {}
    for ins in code.values():
        for t in ins.targets:
            callers.setdefault(t, []).append(ins.addr)
    calls = {t for ins in code.values() if ins.text.startswith(("call", "rst")) for t in ins.targets}

    def label(ad):
        if ad in names:
            return names[ad]
        if ad in calls:
            return "sub_%04X" % ad
        if ad in code:
            return "L%04X" % ad
        return "d_%04X" % ad

    datarefs = {ins.ref for ins in code.values() if ins.ref is not None and a.org <= ins.ref < a.end and ins.ref not in code}

    def fix(text):
        def rep(m):
            v = int(m.group(1), 16)
            if v in callers or v in names or v in datarefs:
                return label(v)
            return m.group(0)
        return re.sub(r"\$([0-9A-F]{4})\b", rep, text)

    out = []
    out.append("; Spellbound (128K) - Mastertronic / MAD 1985, David Jones")
    out.append("; Machine-generated listing from tools/z80dis.py. Code bytes: %d" % sum(i.size for i in code.values()))
    out.append("        org $%04X" % a.org)
    ad = a.org
    while ad < a.end:
        if ad in code:
            ins = code[ad]
            if ad in callers or ad in names:
                out.append("")
                if ad in comments:
                    out.append("; " + comments[ad])
                xr = callers.get(ad, [])
                if xr:
                    out.append("; refs: " + " ".join("%04X" % c for c in sorted(xr)[:12]) + (" ..." if len(xr) > 12 else ""))
                out.append(label(ad) + ":")
            raw = " ".join("%02X" % mem[ad + k] for k in range(ins.size))
            out.append("        %-24s ; %04X  %s" % (fix(ins.text), ad, raw))
            ad += ins.size
        else:
            start = ad
            run = []
            while ad < a.end and ad not in code and len(run) < 8:
                if run and (ad in datarefs or ad in names):
                    break
                run.append(mem[ad])
                ad += 1
            if start in datarefs or start in names:
                out.append(label(start) + ":")
            asc = "".join(chr(c) if 32 <= c < 127 else "." for c in run)
            out.append("        defb %-35s ; %04X  %s" % (",".join("$%02X" % c for c in run), start, asc))
    text = "\n".join(out) + "\n"
    if a.output == "-":
        print(text, end="")
    else:
        open(a.output, "w").write(text)
        print("wrote %s: %d instructions, %d code bytes" % (a.output, len(code), sum(i.size for i in code.values())))


if __name__ == "__main__":
    main()
