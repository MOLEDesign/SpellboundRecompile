"""Amiga picture formats used by Champions of Krynn.

All pictures are planar (one bitplane after another, rows padded to an even
number of bytes). Two encodings exist.

Picture block (entries of DAA files, after DAX run-length decoding)::

    u16 height        rows
    u16 width         in bytes (8 pixel units)
    u16 x, y          default screen position, in 8 pixel units
    u8  count         number of frames, stored side by side in one bitmap
    [u16 palette[32]] 12-bit Amiga colours, present for 5-plane pictures
    bitmap            planes * height * even(width * count)

8x8 symbol sets (8X8D*) are pictures with height 8, width 1 and many frames,
4 planes and no palette; colour 13 is their transparent colour.

Animation blob (entries of pic*.daa / sprit*.daa)::

    u16 n              compressed length of the header
    header (n bytes, DAX run-length): the picture block header above +
                       palette + u16 size[count-1] (frame 2.. lengths - 2)
    frame 0            PackBits, full 5-plane bitmap
    frame 1..count-1   PackBits, each XORed onto frame 0; stored length size+2

Monster sprites (sprit*) have 3 frames: near, middle and far; their
background colour is the transparent one (see transparent_index).
"""
import struct

from .compress import dax_rle, packbits

# The 16 EGA colours: indices 0-15 of every game palette.
EGA = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170),
       (170, 85, 0), (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85),
       (85, 255, 255), (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255)]


def amiga_rgb(c):
    return ((c >> 8 & 15) * 17, (c >> 4 & 15) * 17, (c & 15) * 17)


class Picture:
    """Decoded picture: frames are bytearrays of colour indices (row major)."""

    def __init__(self, width, height, frames, palette=None, x=0, y=0):
        self.width = width            # pixels per frame
        self.height = height
        self.frames = frames
        self.palette = palette        # list of (r,g,b) or None
        self.x, self.y = x, y

    def rgb_palette(self):
        pal = list(self.palette or [])
        if len(pal) < 32:
            pal += (EGA * 2)[len(pal):32]
        return pal


def _planar(data, width_bytes, height, planes, frames_across=1, frame_bytes=None):
    """Planar bitmap -> list of index bytearrays, one per frame (side by side)."""
    rb = width_bytes * frames_across
    rb += rb & 1
    plane_size = rb * height
    fw = (frame_bytes or width_bytes) * 8
    out = [bytearray(fw * height) for _ in range(frames_across)]
    for p in range(planes):
        bit = 1 << p
        base = p * plane_size
        for y in range(height):
            row = data[base + y * rb:base + (y + 1) * rb]
            for f in range(frames_across):
                pix = out[f]
                o = y * fw
                for xb in range(width_bytes):
                    b = row[f * width_bytes + xb] if f * width_bytes + xb < len(row) else 0
                    if not b:
                        continue
                    for k in range(8):
                        if b & (0x80 >> k):
                            pix[o + xb * 8 + k] |= bit
    return out


def decode_block(data):
    """Picture block (already run-length decoded)."""
    h, w, x, y, count = struct.unpack_from('>HHhhB', data)
    if h == 0 or w == 0:
        return None
    rb = w * count
    rb += rb & 1
    body = len(data) - 9
    palette = None
    # 5-plane pictures carry a palette; some blocks end with 2 padding bytes
    if body - 64 >= 5 * rb * h and (body - 64) - 5 * rb * h < rb:
        palette = [amiga_rgb(struct.unpack_from('>H', data, 9 + 2 * i)[0]) for i in range(32)]
        planes, start = 5, 73
    else:
        planes, start = body // (rb * h), 9
    frames = _planar(data[start:], w, h, planes, count)
    return Picture(w * 8, h, frames, palette, x, y)


def decode_anim(blob):
    """Animation blob from pic*.daa / sprit*.daa."""
    n = struct.unpack_from('>H', blob)[0]
    hdr = dax_rle(blob[2:2 + n])
    h, w, x, y, count = struct.unpack_from('>HHhhB', hdr)
    palette = [amiga_rgb(struct.unpack_from('>H', hdr, 9 + 2 * i)[0]) for i in range(32)]
    sizes = list(struct.unpack_from('>%dH' % (count - 1), hdr, 73)) if count > 1 else []
    rest = blob[2 + n:]
    rb = w + (w & 1)
    fsize = rb * h * 5
    first = len(rest) - sum(sizes) - 2 * len(sizes)
    base = packbits(rest[:first], fsize)
    bitmaps = [base]
    pos = first
    for s in sizes:
        delta = packbits(rest[pos:pos + s + 2], fsize)
        pos += s + 2
        bitmaps.append(bytes(a ^ b for a, b in zip(base, delta)))
    frames = [_planar(bm, w, h, 5)[0] for bm in bitmaps]
    return Picture(w * 8, h, frames, palette, x, y)


def transparent_index(pic):
    """Most common colour on the border of frame 0 (sprite background key)."""
    f = pic.frames[0]
    W, H = pic.width, pic.height
    counts = {}
    for x in range(W):
        for yy in (0, H - 1):
            c = f[yy * W + x]
            counts[c] = counts.get(c, 0) + 1
    return max(counts, key=counts.get)


def to_rgb(pic, frame=0, transparent=None):
    pal = pic.rgb_palette()
    return [(0, 0, 0, 0) if c == transparent else pal[c] + (255,) for c in pic.frames[frame]]


def save_png(path, pic, transparent=None, frames=None, scale=1):
    """Write all (or the given) frames side by side."""
    from .png import write_png
    frames = range(len(pic.frames)) if frames is None else frames
    frames = list(frames)
    W, H = pic.width, pic.height
    rows = [to_rgb(pic, f, transparent) for f in frames]
    out = []
    for y in range(H * scale):
        sy = y // scale
        for r in rows:
            line = r[sy * W:(sy + 1) * W]
            for x in range(W * scale):
                out.append(line[x // scale])
    write_png(path, W * len(frames) * scale, H * scale, out, alpha=True)
