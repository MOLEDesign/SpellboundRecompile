# Spellbound – the remake

A from-scratch remake of Spellbound (1986) for macOS, written in Python 3
with [pygame-ce](https://pyga.me). Unlike the emulated build in `src/`,
none of the original Z80 code runs here. Movement, rooms, the lift,
characters, the window menus, spells and the quest are all new code.

What it reuses is the original game's **data**: all 57 rooms with their
scenery and collision maps, the sprites, the font, every object and
character with their starting positions, the game's own text (menus,
messages, scrolls, spells) and Rob Hubbard's title music. `bake.py`
extracts that once from your own copy of the tape into `remake/data/`.
That folder is git-ignored and must not be shared.

## Play

```sh
pip3 install pygame-ce
python3 remake/bake.py original/S_BND128.TAP     # once (needs a C compiler: xcode-select --install)
python3 remake/spellbound.py
```

Or double-click `remake/run.command` in Finder. It installs pygame-ce,
bakes the data if needed (looking for `S_BND128.TAP` in `remake/` or
`original/`), then starts the game. From the repo root, `make remake` does
the same.

| key                  | action                                   |
|----------------------|------------------------------------------|
| ← → or N M           | walk                                      |
| ↑ or A               | jump (hold to keep jumping)               |
| Space / Return       | command menu, choose                      |
| ↑ ↓ (A Z)            | move the pointer in menus                 |
| Esc                  | cancel / back to the main menu            |
| F5 / F9              | save / load (`~/.spellbound_remake_save.json`) |
| F2                   | music on/off                              |
| F11                  | full screen                               |
| ⌘Q                   | quit                                      |

A game controller works too: D-pad or stick to walk, button A to fire,
button B to cancel.

## The quest

As in the original, Gimbal the wizard has trapped himself in a white-out
spell and summoned seven people into the Castle of Karn. Free Gimbal, then
send everybody home. On the way you will fix the lift and protect yourself
against a candle and a gas room. You'll also bring down a wall, build your
way over the Tower, open a secret tunnel, cross a pit and mend a talisman.
The characters help if you treat them well: keep them awake, fed and
happy. You need the WAND OF COMMAND to give them orders, and the ELF-HORN
summons them. Your strength drains slowly: the BOTTLE OF LIQUID
(restorative fluid) helps, especially if somebody looks after it for you.

Reading things and looking into the crystal ball gives hints. The original
game's walkthrough also works for the remake.

## How it is built

```
bake.py                 data pack builder (runs tools/bake_remake + decodes the tape)
spellbound.py           window, input, 50 Hz loop, music
sbremake/assets.py      data loading, ZX palette, original font, text formatting
sbremake/ui.py          framed windows and pointer menus
sbremake/world.py       collision, Magic Knight's movement (speeds/jump measured from the original)
sbremake/game.py        rules: objects, characters, lift, commands, spells, puzzles
tests/reachability.py   walks the whole castle with the real physics: every room/object reachable
tests/playthrough.py    plays the complete quest through the command functions
```

The data pack holds:

* **Room backdrops and collision.** The original engine runs in the
  emulator (`tools/bake_remake.c`), and each room is captured just before
  objects and characters are drawn.
* **Everything else, decoded straight from the tape:** sprites (graphics
  table at C544), the dictionary-compressed text (bank 6), exits (982A),
  objects (635C/9A1D), characters (6344/62CA/631C) and the font (B700).
  See `../docs/ANALYSIS.md`.

The rules are based on the original's texts and walkthrough, not
translated from its code. Characters' moods, the clock and some minor
behaviours are simplified.

Tests: `make remake-test` (or run the two scripts in `tests/`).
