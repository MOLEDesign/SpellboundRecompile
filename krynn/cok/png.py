"""Minimal PNG writer (RGB/RGBA rows), no dependencies."""
import os
import struct
import zlib


def write_png(path, width, height, pixels, alpha=False):
    """pixels: flat list of (r,g,b) or (r,g,b,a) tuples, row major."""
    bpp = 4 if alpha else 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for p in pixels[y * width:(y + 1) * width]:
            raw += bytes(p[:bpp])

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)

    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6 if alpha else 2, 0, 0, 0)))
        f.write(chunk(b'IDAT', zlib.compress(bytes(raw), 9)))
        f.write(chunk(b'IEND', b''))
