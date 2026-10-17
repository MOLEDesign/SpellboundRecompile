#!/usr/bin/env python3
"""Amiga hunk executable loader.

Parses HUNK_HEADER executables, applies HUNK_RELOC32 and lays every hunk
out in one flat big-endian image (each hunk at an aligned address starting
at BASE), the way the OS loader would. Symbols (HUNK_SYMBOL) are kept.

    python3 hunk.py info game
    python3 hunk.py flat game out.bin      # writes image + out.bin.map
"""
import struct
import sys

HUNK_UNIT, HUNK_NAME, HUNK_CODE, HUNK_DATA, HUNK_BSS = 0x3e7, 0x3e8, 0x3e9, 0x3ea, 0x3eb
HUNK_RELOC32, HUNK_RELOC16, HUNK_RELOC8 = 0x3ec, 0x3ed, 0x3ee
HUNK_EXT, HUNK_SYMBOL, HUNK_DEBUG, HUNK_END, HUNK_HEADER = 0x3ef, 0x3f0, 0x3f1, 0x3f2, 0x3f3
HUNK_DREL32, HUNK_RELOC32SHORT = 0x3f7, 0x3fc
KIND = {HUNK_CODE: 'CODE', HUNK_DATA: 'DATA', HUNK_BSS: 'BSS'}
BASE = 0x10000


class Hunk:
    def __init__(self, index, alloc):
        self.index = index
        self.alloc = alloc            # bytes reserved
        self.kind = None
        self.data = bytearray()
        self.relocs = []              # (offset, target hunk)
        self.symbols = []             # (name, offset)
        self.addr = 0


class HunkFile:
    def __init__(self, raw):
        self.raw = raw
        self.pos = 0
        if self._u32() != HUNK_HEADER:
            raise ValueError('not a hunk executable')
        while self._u32():            # resident library names (none)
            pass
        _, first, last = self._u32(), self._u32(), self._u32()
        self.hunks = [Hunk(i, (self._u32() & 0x3fffffff) * 4) for i in range(last - first + 1)]
        i = 0
        while self.pos < len(raw) and i < len(self.hunks):
            t = self._u32() & 0x3fffffff
            h = self.hunks[i]
            if t in (HUNK_CODE, HUNK_DATA):
                h.kind = KIND[t]
                size = self._u32() * 4
                h.data = bytearray(raw[self.pos:self.pos + size])
                self.pos += size
            elif t == HUNK_BSS:
                h.kind = 'BSS'
                self._u32()
            elif t == HUNK_RELOC32:
                while True:
                    cnt = self._u32()
                    if not cnt:
                        break
                    target = self._u32()
                    for _ in range(cnt):
                        h.relocs.append((self._u32(), target))
            elif t in (HUNK_RELOC32SHORT, HUNK_DREL32):
                while True:
                    cnt = self._u16()
                    if not cnt:
                        break
                    target = self._u16()
                    for _ in range(cnt):
                        h.relocs.append((self._u16(), target))
                if self.pos & 2:
                    self.pos += 2
            elif t == HUNK_SYMBOL:
                while True:
                    nl = self._u32()
                    if not nl:
                        break
                    name = raw[self.pos:self.pos + nl * 4].rstrip(b'\0').decode('latin-1')
                    self.pos += nl * 4
                    h.symbols.append((name, self._u32()))
            elif t == HUNK_DEBUG:
                self.pos += self._u32() * 4
            elif t == HUNK_NAME:
                self.pos += self._u32() * 4
            elif t == HUNK_END:
                i += 1
            else:
                raise ValueError('unsupported hunk type %#x at %#x' % (t, self.pos - 4))
        self.layout()

    def _u32(self):
        v = struct.unpack_from('>I', self.raw, self.pos)[0]
        self.pos += 4
        return v

    def _u16(self):
        v = struct.unpack_from('>H', self.raw, self.pos)[0]
        self.pos += 2
        return v

    def layout(self, base=BASE):
        a = base
        for h in self.hunks:
            h.addr = a
            a += (max(h.alloc, len(h.data)) + 0xff) & ~0xff
        self.end = a

    def image(self):
        """Flat relocated memory image starting at BASE."""
        img = bytearray(self.end - BASE)
        for h in self.hunks:
            d = bytearray(h.data)
            for off, tgt in h.relocs:
                v = struct.unpack_from('>I', d, off)[0]
                struct.pack_into('>I', d, off, (v + self.hunks[tgt].addr) & 0xffffffff)
            img[h.addr - BASE:h.addr - BASE + len(d)] = d
        return bytes(img)

    def reloc_sites(self):
        """Absolute addresses of every relocated longword (pointers)."""
        return {h.addr + off for h in self.hunks for off, _ in h.relocs}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    hf = HunkFile(open(argv[2], 'rb').read())
    if argv[1] == 'info':
        for h in hf.hunks:
            print('%3d %-4s %06x size %6d alloc %6d relocs %5d syms %d' % (
                h.index, h.kind, h.addr, len(h.data), h.alloc, len(h.relocs), len(h.symbols)))
        return 0
    open(argv[3], 'wb').write(hf.image())
    with open(argv[3] + '.map', 'w') as f:
        for h in hf.hunks:
            f.write('hunk %d %s %06x %d\n' % (h.index, h.kind, h.addr, max(h.alloc, len(h.data))))
            for name, off in h.symbols:
                f.write('  %06x %s\n' % (h.addr + off, name))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
