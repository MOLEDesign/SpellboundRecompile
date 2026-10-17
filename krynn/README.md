# Champions of Krynn (Amiga) — decompile and Python remake

A personal project to take the 1990 SSI/TSR Gold Box game apart and rebuild
it in Python, so its worst flaws can be fixed.

> The game is **not** in this repository. Put your own copy (the `.zip` of
> ADF images, or the `.adf` files) in `krynn/original/`. `.gitignore` keeps
> it, and everything extracted from it, out of git.

## What works now

* **Every data format decoded** (see [docs/FORMATS.md](docs/FORMATS.md)):
  disk images, DAX/DAA containers, all pictures (big pictures, animated
  portraits, 3-distance monster sprites, combat icons, wall tiles), IFF
  screens, 3D maps, wall sets, and the ECL event-script language.
* **Extractor**: `python3 tools/extract.py` writes `extracted/` with every
  picture as PNG, the wall sets, the maps (ASCII and PNG), all 22 ECL
  scripts as readable listings, and an annotated 68000 disassembly of the
  executable (`pip install capstone`).
* **Remake** (`remake/`): runs the original event scripts in a new ECL
  virtual machine. You get the story text, menus, the original pictures and
  animations, the overland map, monster sprites, and the first-person 3D
  view with the original walls. New: readable text, mouse support, and an
  automap of the squares you have visited (M).

## What does not work yet

The parts of the original engine that live in `game` rather than in the
scripts are still to be rebuilt:

* character creation and the character sheet (the party is loaded from the
  save disk)
* tactical combat (a placeholder screen declares victory)
* items, treasure, shops, training, spells, resting rules
* sound and music
* saving and loading

## Play

```sh
pip3 install pygame-ce
python3 remake/krynn.py            # finds krynn/original/*.zip by itself
```

| key | action |
|-----|--------|
| ↑ / W | forward (overland: north) |
| ← → / A D | turn (overland: west/east) |
| ↓ / S | turn around (overland: south) |
| L | search/look |
| M | automap on/off |
| RETURN / SPACE, or a letter | choose a menu option (mouse works too) |
| F11 | full screen |
| ESC | quit |

`python3 remake/play_text.py` plays the same scripts in the terminal.

## Tools

```sh
python3 tools/adf.py list "original/Champions of Krynn A.adf"
python3 tools/extract.py                 # -> extracted/
python3 tools/hunk.py info extracted/files/game
python3 tools/disasm68k.py extracted/files/game -o krynn.asm
python3 tests/run_tests.py               # format and script checks against your disks
```

## Layout

```
cok/            format library: adf, dax, compress, gfx, ilbm, geo, view3d, ecl, gamefiles, png
tools/          extract.py, adf.py, hunk.py, disasm68k.py (+ labels68k.txt)
remake/         krynn.py (pygame), play_text.py, kroc/ (vm, world, app), fonts/
docs/           FORMATS.md
tests/          run_tests.py
```
