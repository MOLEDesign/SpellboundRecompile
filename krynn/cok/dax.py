"""Gold Box resource containers.

Three layouts occur on the Amiga disks:

* ``.DAX`` (PC heritage, little endian): u16 header length, then 9-byte
  entries ``id:u8 offset:u32 raw:u16 comp:u16``; data follows the header.
  Each entry is compressed with the DAX run-length scheme.
* ``.DAA`` (Amiga, big endian): u16 header length *including* the length
  field, same 9-byte entries, data starts at that length.
* ``.DAA`` animation files (pic*, sprit*): u16 header length, 6-byte entries
  ``id:u8 0:u8 offset:u32``. Each entry is a self-describing blob
  (see gfx.decode_anim); sizes come from the next entry's offset.
"""
import struct

from .compress import dax_rle


class Entry:
    __slots__ = ('id', 'offset', 'raw_size', 'comp_size')

    def __init__(self, id, offset, raw_size, comp_size):
        self.id, self.offset, self.raw_size, self.comp_size = id, offset, raw_size, comp_size


class Container:
    def __init__(self, data, name=''):
        self.name = name
        self.data = data
        self.entries = {}
        self.order = []
        self.kind = None
        if name.upper().endswith('.DAX'):
            self._parse9(struct.unpack_from('<H', data)[0] + 2, '<', 2)
        elif not self._try9():
            self._parse6()

    def _try9(self):
        n = struct.unpack_from('>H', self.data)[0]
        if (n - 2) % 9:
            return False
        ents = [struct.unpack_from('>BIHH', self.data, 2 + 9 * k) for k in range((n - 2) // 9)]
        pos = 0
        for _, off, raw, comp in ents:
            if off != pos:
                return False
            pos += comp
        if n + pos != len(self.data):
            return False
        self._parse9(n, '>', 2)
        return True

    def _parse9(self, base, endian, first):
        self.kind = 'dax' if endian == '<' else 'daa'
        self.base = base
        for k in range((base - first) // 9):
            i, off, raw, comp = struct.unpack_from(endian + 'BIHH', self.data, first + 9 * k)
            self._add(Entry(i, off, raw, comp))

    def _parse6(self):
        self.kind = 'anim'
        n = struct.unpack_from('>H', self.data)[0]
        self.base = n
        ents = [struct.unpack_from('>BBI', self.data, 2 + 6 * k) for k in range((n - 2) // 6)]
        ends = [e[2] for e in ents[1:]] + [len(self.data) - n]
        for (i, _, off), end in zip(ents, ends):
            self._add(Entry(i, off, None, end - off))

    def _add(self, e):
        self.entries[e.id] = e
        self.order.append(e.id)

    def ids(self):
        return list(self.order)

    def raw(self, id):
        e = self.entries[id]
        return self.data[self.base + e.offset:self.base + e.offset + e.comp_size]

    def get(self, id):
        """Decompressed bytes for DAX/DAA entries, the raw blob for animation files."""
        e = self.entries[id]
        if self.kind == 'anim':
            return self.raw(id)
        return dax_rle(self.raw(id), e.raw_size)

    def __contains__(self, id):
        return id in self.entries
