#!/usr/bin/env python3
"""Extract the Spellbound 128K TAP into raw memory images.

The BASIC loader (block 0) does this:
    CLEAR 26200
    LOAD "" SCREEN$                     -> loading screen
    for A in 1,3,4,6:
        LOAD "" CODE  (16K at 32768)    -> copied by a tiny stub at 26210
        into 128K bank A at 0xC000       (OUT 0x7FFD,A ; LDIR 8000->C000)
    LOAD "" CODE  (26240, 39295 bytes)  -> main program
    RANDOMIZE USR 26627                  -> entry point

Outputs (in --out, default ./extracted):
    loader.bas.bin   raw BASIC program
    screen.scr       6912 byte loading screen
    bank1.bin bank3.bin bank4.bin bank6.bin
    main.bin         39295 bytes loaded at 26240 (0x6680)
    ram48.bin        64K image of the CPU address space at the moment of
                     RANDOMIZE USR 26627 (ROM area left as zero)
"""
import argparse
import os
import sys

MAIN_ADDR = 26240
ENTRY = 26627
BANK_ORDER = [1, 3, 4, 6]


def read_tap(path):
    data = open(path, "rb").read()
    blocks, i = [], 0
    while i < len(data):
        n = data[i] | data[i + 1] << 8
        blk = data[i + 2:i + 2 + n]
        x = 0
        for c in blk:
            x ^= c
        if x != 0:
            raise ValueError("bad checksum in block %d" % len(blocks))
        blocks.append(blk)
        i += 2 + n
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tap")
    ap.add_argument("--out", default="extracted")
    a = ap.parse_args()
    blocks = read_tap(a.tap)
    payload = [b[1:-1] for b in blocks if b[0] == 0xFF]
    if len(payload) != 7:
        sys.exit("unexpected TAP layout: %d data blocks" % len(payload))
    os.makedirs(a.out, exist_ok=True)

    def w(name, d):
        open(os.path.join(a.out, name), "wb").write(bytes(d))
        print("wrote %-14s %6d bytes" % (name, len(d)))

    w("loader.bas.bin", payload[0])
    w("screen.scr", payload[1])
    for bank, d in zip(BANK_ORDER, payload[2:6]):
        w("bank%d.bin" % bank, d)
    main_code = payload[6]
    w("main.bin", main_code)

    ram = bytearray(65536)
    ram[0x4000:0x4000 + 6912] = payload[1]
    ram[MAIN_ADDR:MAIN_ADDR + len(main_code)] = main_code
    w("ram48.bin", ram)
    print("entry point: %d (0x%04X)" % (ENTRY, ENTRY))


if __name__ == "__main__":
    main()
