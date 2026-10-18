#!/usr/bin/env python3
"""Champions of Krynn remake (Python + pygame-ce).

    pip3 install pygame-ce
    python3 krynn.py [path to your .zip / .adf folder] [--size WxH] [--fullscreen] [--load A]

Keys: arrows/WASD move and turn, L search, RETURN/SPACE choose,
first letter picks a menu item, F5 save, F9 load, F11 full screen, ESC quit.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', nargs='?')
    ap.add_argument('--size', help='window size, e.g. 1600x900 (default: 1920x1080 or what fits)')
    ap.add_argument('--fullscreen', action='store_true')
    ap.add_argument('--load', metavar='SLOT', help='start from saved game A-J')
    a = ap.parse_args()
    from kroc.app import App
    size = tuple(int(v) for v in a.size.lower().split('x')) if a.size else None
    app = App(a.source, size, a.fullscreen)
    if a.load:
        app.load_game(a.load.upper())
    app.run()


if __name__ == '__main__':
    main()
