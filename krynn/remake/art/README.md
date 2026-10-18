# Replaceable combat art

Every block on the overhead combat map has a fixed id: walls, doors, floors
and outdoor obstacles. [BLOCKS.md](BLOCKS.md) lists them all and says what
each one is.

To redraw a block, save a PNG named after its id in `blocks/`, for example
`blocks/W1-01-03.png`. Any size works; it is scaled to the cell, so square
images look best, and transparency is kept. The game uses your picture
wherever that block appears and falls back to the built-in look for the rest.

Built-in looks:

* walls are solid blocks in the average colour of the original wall, with
  the id printed on them, so you can see which id a block on screen has
  (zoom in with V);
* doors are wooden blocks; a locked door gets a dark lock mark;
* floors and outdoor trees, bushes, logs and rocks use the original 24x24
  combat tiles.

To see what each wall looked like in the original game, run
`python3 tools/extract.py` and open `extracted/blocks/index.md`. It shows one
reference picture per id: the wall as the 3D view draws it, or the original
tile.

Id scheme (also in `cok/blocks.py`):

| id | meaning |
|----|---------|
| `W<area>-<walldef>-<nn>` | wall style `nn` (1-15) of WALLDEF entry `walldef` (hex) on disk area 1 or 2 |
| `D<area>-<walldef>-<nn>` | a door in that wall |
| `EDGE` | beyond the edge of the 16x16 map |
| `F-DUNG` | dungeon floor |
| `F-WILD-<nn>` | outdoor ground, WILDCOM tile `nn` |
| `O-WILD-<nn>` | outdoor obstacle, WILDCOM tile `nn` |
