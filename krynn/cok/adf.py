"""Amiga ADF disk images (AmigaDOS OFS/FFS file systems), no dependencies."""
import struct

BSIZE = 512
T_HEADER, T_DATA, T_LIST = 2, 8, 16
ST_ROOT, ST_DIR, ST_FILE = 1, 2, -3


def _u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def _s32(b, o):
    return struct.unpack_from('>i', b, o)[0]


class ADF:
    def __init__(self, data):
        if len(data) not in (901120, 1802240):
            raise ValueError('not a DD/HD ADF image (%d bytes)' % len(data))
        if data[:3] != b'DOS':
            raise ValueError('not an AmigaDOS disk (custom bootblock / track loader)')
        self.data = data
        self.ffs = bool(data[3] & 1)
        self.nblocks = len(data) // BSIZE
        self.root = self.nblocks // 2
        rb = self.block(self.root)
        self.label = rb[433:433 + rb[432]].decode('latin-1')

    def block(self, n):
        return self.data[n * BSIZE:(n + 1) * BSIZE]

    @staticmethod
    def _name(b):
        return b[433:433 + min(b[432], 30)].decode('latin-1')

    def _entries(self, dirblock):
        b = self.block(dirblock)
        for i in range(72):
            n = _u32(b, 24 + 4 * i)
            while n:
                e = self.block(n)
                yield n, e
                n = _u32(e, 496)          # hash chain

    def walk(self, dirblock=None, prefix=''):
        """Yield (path, size, header_block) for every file, depth first."""
        for n, e in sorted(self._entries(dirblock or self.root),
                           key=lambda t: self._name(t[1]).lower()):
            name = prefix + self._name(e)
            st = _s32(e, 508)
            if st == ST_DIR:
                yield name + '/', 0, n
                yield from self.walk(n, name + '/')
            elif st == ST_FILE:
                yield name, _u32(e, 324), n

    def read(self, header):
        h = self.block(header)
        size = _u32(h, 324)
        blocks = []
        b = h
        while True:
            cnt = _u32(b, 8)
            # data block pointers are stored backwards from offset 308
            blocks += [_u32(b, 308 - 4 * i) for i in range(cnt)]
            ext = _u32(b, 504)
            if not ext:
                break
            b = self.block(ext)
        out = bytearray()
        for n in blocks:
            d = self.block(n)
            if self.ffs:
                out += d
            else:
                out += d[24:24 + _u32(d, 12)]
        return bytes(out[:size])

    def files(self):
        for path, size, hdr in self.walk():
            if not path.endswith('/'):
                yield path, self.read(hdr)
