"""The two run-length schemes used by the game's data files."""


def dax_rle(src, size=None):
    """Gold Box DAX/DAA scheme: n<0x80 -> copy n+1 literals; n>=0x80 -> repeat next byte 256-n times."""
    out = bytearray()
    i, n = 0, len(src)
    limit = size if size is not None else 1 << 30
    while i < n and len(out) < limit:
        r = src[i]
        if r < 0x80:
            out += src[i + 1:i + 2 + r]
            i += r + 2
        else:
            out += bytes((src[i + 1],)) * (256 - r)
            i += 2
    return bytes(out[:limit]) if size is not None else bytes(out)


def packbits(src, size=None):
    """Amiga ByteRun1 / PackBits: n<0x80 -> n+1 literals; 0x80 nop; else repeat 257-n times."""
    out = bytearray()
    i, n = 0, len(src)
    limit = size if size is not None else 1 << 30
    while i < n and len(out) < limit:
        r = src[i]
        if r < 0x80:
            out += src[i + 1:i + 2 + r]
            i += r + 2
        elif r == 0x80:
            i += 1
        else:
            out += bytes((src[i + 1],)) * (257 - r)
            i += 2
    return bytes(out[:limit]) if size is not None else bytes(out)
