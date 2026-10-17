#!/usr/bin/env python3
"""Champions of Krynn remake (Python + pygame-ce).

    pip3 install pygame-ce
    python3 krynn.py [path to your .zip / .adf folder] [--scale N] [--fullscreen]

Keys: arrows/WASD move and turn, L search, M automap, RETURN/SPACE choose,
first letter picks a menu item, F11 full screen, ESC quit.
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
    ap.add_argument('--scale', type=int, default=3)
    ap.add_argument('--fullscreen', action='store_true')
    a = ap.parse_args()
    from kroc.app import App
    App(a.source, a.scale, a.fullscreen).run()


if __name__ == '__main__':
    main()
