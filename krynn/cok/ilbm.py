"""IFF ILBM (Deluxe Paint .LBM) decoder: BMHD, CMAP, BODY (PackBits or raw)."""
import struct

from .compress import packbits


class ILBM:
    def __init__(self, data):
        if data[:4] != b'FORM' or data[8:12] not in (b'ILBM', b'PBM '):
            raise ValueError('not an IFF ILBM')
        self.palette = []
        self.chunks = {}
        pos = 12
        while pos + 8 <= len(data):
            cid = data[pos:pos + 4]
            size = struct.unpack_from('>I', data, pos + 4)[0]
            self.chunks[cid.decode('latin-1')] = data[pos + 8:pos + 8 + size]
            pos += 8 + size + (size & 1)
        (self.width, self.height, self.x, self.y, self.planes, self.masking,
         self.compression, _, self.transparent, _, _, self.page_w, self.page_h) = \
            struct.unpack('>HHhhBBBBHBBhh', self.chunks['BMHD'][:20])
        cmap = self.chunks.get('CMAP', b'')
        self.palette = [tuple(cmap[i:i + 3]) for i in range(0, len(cmap) - 2, 3)]
        self.pixels = self._body()

    def _body(self):
        body = self.chunks['BODY']
        rb = ((self.width + 15) // 16) * 2
        nplanes = self.planes + (1 if self.masking == 1 else 0)
        need = rb * nplanes * self.height
        raw = packbits(body, need) if self.compression == 1 else body[:need]
        pix = bytearray(self.width * self.height)
        for y in range(self.height):
            for p in range(self.planes):
                row = raw[(y * nplanes + p) * rb:(y * nplanes + p + 1) * rb]
                bit = 1 << p
                for x in range(self.width):
                    if row[x >> 3] & (0x80 >> (x & 7)):
                        pix[y * self.width + x] |= bit
        return bytes(pix)
