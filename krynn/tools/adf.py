#!/usr/bin/env python3
"""Read files from Amiga ADF disk images (OFS and FFS, no dependencies).

    python3 adf.py list  DISK.adf
    python3 adf.py extract DISK.adf OUTDIR
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from cok.adf import ADF  # noqa: E402


def main(argv):
    if len(argv) < 3 or argv[1] not in ('list', 'extract'):
        print(__doc__)
        return 1
    adf = ADF(open(argv[2], 'rb').read())
    if argv[1] == 'list':
        print('%s (%s)' % (adf.label, 'FFS' if adf.ffs else 'OFS'))
        for path, size, _ in adf.walk():
            print('%8s  %s' % ('' if path.endswith('/') else size, path))
        return 0
    for path, data in adf.files():
        p = os.path.join(argv[3], *path.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
