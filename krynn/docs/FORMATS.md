# Champions of Krynn (Amiga): file formats and engine notes

Everything here was worked out from the game's own disks. The PC Gold Box
engine is closely related, and the public reverse-engineering work on
*Curse of the Azure Bonds* (the `coab` project) was used as a reading
reference for the rendering and script rules. The code here is new.

## Disks

Three AmigaDOS (OFS) disks plus a save disk. `cok/adf.py` reads them.

| disk | contents |
|------|----------|
| 1 `Disk One`   | `game` (480 KB hunk executable), title/intro `.lbm`, common `.DAA`, sound samples |
| 2 `Disk Two`   | area 1: `ECL1 GEO1 WALLDEF1 ITEM1 MON1*` (`.DAX`), `PIC1 SPRIT1 BIGPIC1 CPIC1 8X8D1` (`.DAA`) |
| 3 `Disk Three` | area 2: the same set with `2`, plus `save/` (a party: `CHRDATA*.sav`, `savgamA.dat`) |

## Containers (`cok/dax.py`)

* `.DAX`: little-endian PC layout. `u16 headerLength`, then 9-byte entries
  `id u8, offset u32, rawSize u16, compSize u16`. Data starts after the header.
* `.DAA`: the same entries, big endian. Here the header length *includes*
  the 2-byte length field.
* animation `.DAA` (`pic*`, `sprit*`): `u16 headerLength`, 6-byte entries
  `id u8, 0, offset u32`. Each entry is one animation blob.

Compression (`cok/compress.py`): DAX run-length (`n<0x80` gives n+1
literal bytes; otherwise the next byte repeats `256-n` times) and Amiga
PackBits (repeats `257-n`, `0x80` is a no-op).

## Pictures (`cok/gfx.py`)

Picture block (after decompression): `u16 height, u16 widthBytes, u16 x,
u16 y, u8 frameCount`. 5-plane pictures then carry a 32-entry 12-bit
palette. The bitmap is planar (all of plane 0, then plane 1, and so on),
rows are padded to even bytes, and the frames sit side by side. 8x8 symbol
sets (`8X8D*`) use the same layout with 4 planes and no palette. Colour 13
is transparent there.

Animation blob: `u16 n` + DAX-compressed header (the picture header +
palette + `u16 size[count-1]`). Frame 0 follows as PackBits. Each later
frame is a PackBits XOR delta against frame 0, stored in `size+2` bytes.
Monster sprites have 3 frames (near, middle and far); their background
colour is transparent.

Palette indices 0-15 are the EGA colours in every picture.

The `.lbm` files are ordinary IFF ILBM (`cok/ilbm.py`).

## Maps (`cok/geo.py`)

GEO entries are 0x402 bytes: a 2-byte header, then four 16x16 planes:

| offset | meaning |
|--------|---------|
| 0x000 | high nibble: wall type facing N; low nibble: E |
| 0x100 | high nibble: wall type facing S; low nibble: W |
| 0x200 | per-square flags |
| 0x300 | door bits, 2 per side (N, E, S, W from bit 0): 0 solid, 1 open door, 2 locked, 3 barred |

Wall type `t` (1-15) is style `(t-1)%5` of wall slot `(t-1)//5`. WALLDEF
entries hold one or more 780-byte wall sets (5 styles x 156 symbol ids). A
set with several parts fills consecutive slots. Its 8x8 symbols come from
`8X8D` entry `id*10+k+1`, or `id` when it has one part. Symbol ids are
global (`0x01` common set `8X8D0:0xCB`, `0x2E` slot 1, `0x74` slot 2,
`0xBA` slot 3), shifted by the starting slot. `cok/view3d.py` draws the
88x88 first-person view from 10 patch kinds, back to front.

## ECL event scripts (`cok/ecl.py`)

Bytecode loaded at VM address 0x8000. Operands carry a type byte:
`0` byte, `1`/`3` memory word read, `2` immediate word, `0x80` packed
6-bit string, `0x81` string variable. Every block starts with 5 entry
points: *run* (after each move), *search* (after the move is drawn),
pre-camp, camp-interrupted and *init*. Krynn has 66 opcodes. 0x00-0x40
match the PC engine, and 0x41 is `ADD EP` (award experience). The
executable still holds the opcode name table at 0x44100.

Memory map: `4B00-4EFF` world flags (`4BE6` in-3D flag, `4BF2` previous
block, `4BC3/4BC4` overland X/Y, `4BC5` loaded GEO), `7A00-7BFF` strings
(`7B2C` current place name), `7C00-7FFF` more state and the selected
character, `8000-9DFF` the block itself, `C04B/C04C/C04D` party X/Y/facing.

A new game starts in block `0x24` ("At the Inn of the Last Home in
Solace..."). Block `0x10` is the overland map, a 38x15 grid over big
picture `0x79`, with a place table at `0x8E72`. Block `0x11` is the first
outpost, and `0x20` is Throtl.

## Monsters, characters and combat graphics

Monster records (`MONnCHA.DAX`, 409 bytes, id = monster number):

| offset | field |
|--------|-------|
| 0x00 | name (length byte + 15 chars) |
| 0x10 | six stat pairs (current, maximum) |
| 0x1E-0x58 | spells it can cast (game spell numbers 1-94, 0 = none) |
| 0x59 | 60 - THAC0 |
| 0x62 | hit points |
| 0xD0 | five saving throws (0xD4: against spells) |
| 0xD5 | movement (flying speeds included) |
| 0xD6 | hit dice |
| 0x10B/0x10C | half-attacks per round of attack groups 1 and 2 |
| 0x10D/0x10E | damage dice count, 0x10F/0x110 dice size, 0x111/0x112 bonus |
| 0x113 | 60 - AC |
| 0x130 | experience value (u16 LE) |

For example, black dragon: 1d4/1d4 claws (4 half-attacks), 3d6 bite, AC 3.

Party records (`save/CHRDATAn.SAV`, 426 bytes) use a shifted layout:
0x00 name, 0x10 stats, 0x1E-0x59 memorised spells (1-94; larger values are
not spells), 0x5A 60 - base THAC0, 0x5B race, 0x5C class, 0x64 maximum HP,
0x5E deity (clerics), 0x5F mage order (1 White Robes, 2 Red, 3 Black,
0 none), 0x66-0xC3 spellbook: one byte per spell number at 0x65 + id (the
mage's grimoire, the cleric's prayers), 0xFE-0x105 levels (cleric, druid,
fighter, paladin, ranger, magic-user, thief, knight), 0x11E experience (u32), 0x141-0x14B combat icon (head,
body, slot, size 1 small / 2 normal, six colour bytes), 0x19B 60 - THAC0
with bonuses, 0x19C 60 - AC, 0x1A0/0x1A2 weapon dice, 0x1A5 damage bonus,
0x1A8 current HP, 0x1A9 movement.

Combat icons: monster id `n` in `CPICn.DAA` is the ready pose and `n|0x80`
is the attack pose. They are 24x24, or 48x24 / 24x48 for big monsters.
Party icons are built from `charT.LBM` (`charS.LBM` for small races), a
sheet of 24x24 cells 13 to a row: body cell = icon body byte, head cell =
67 + head byte. Template colours 1, 2, 3, 4, 6, 7 (and +8) are replaced by
the six colour bytes (low and high nibble). Colour 16 is the background.

Combat tiles: `DUNGCOM`, `WILDCOM` and `RANDCOM` hold 24x24 tiles as
5-plane pictures with a palette and 2 padding bytes. The original lays
the 13x5 map squares around the party into a skewed 50x25 grid, which is
the fake isometric view. The remake draws the same area straight from
above (`remake/kroc/combat.py`).

## Script variables for camping

`C04F` is the flags byte of the party's map square (the third GEO plane);
the low six bits number the rooms and areas of the map, and scripts test
them for room events and safe places to rest. Each block's `precamp` entry
sets `7ED3` (chance in percent that a rest is interrupted) and `7ED2`
(how often it is checked; 0 = never), and its `campint` entry is run when
a rest is interrupted (usually an ambush from the block's monster table).

## Spells

Spell numbers 1-94 follow the spell-name list in the executable (1 Bless,
3 Cure Light Wounds, 15 Magic Missile, 21 Sleep, 23 Hold Person (cleric),
34 Stinking Cloud, 47 Fireball, 51 Lightning Bolt, 55 Slow ...); a few
names repeat for scroll and item versions. The full table, with each
spell's shape, range and effect as the remake plays it, is
`remake/kroc/spells.py`.

## Items

`items` on disk 1 is the item type table: a 2-byte header, then 128
records of 16 bytes, indexed by item type:

| byte | meaning |
|------|---------|
| 0 | slot (0 weapon, 1 shield, 2 armour, 10 ammunition and other) |
| 1 | hands needed |
| 2/3/4 | damage dice, size and bonus vs large creatures |
| 5 | half-attacks per round (bows 4 = 2 shots, darts 6 = 3) |
| 9/10/11 | damage dice, size and bonus vs normal creatures |
| 12 | range in combat squares (0 = melee only) |
| 13 | classes allowed |
| 14 | flags: 0x01 uses arrows, 0x02 missile, 0x04 melee, 0x10 throwable, 0x80 uses quarrels |

Weapon types 1-30 follow the order of the item-name word list in the
executable (1 Battle Axe ... 18 Long Sword, 25 Short Bow, 27 Light
Crossbow, 28 Sling, 30 Arrow). 67 is the kender hoopak.

Byte 6 is the armour value: `(b & 0x7F) - 0x32` for body armour (leather
2, ring 3, scale 4, chain 5, banded 6, plate 7, Solamnic plate 10) and
`b & 0x7F` for what is worn over it (shield 1). AC = 10 - armour - plus -
dexterity bonus reproduces every saved character's AC.

Item records are 63 bytes in `ITEMn.DAX` and `MONnITM.DAX` (little-endian)
and 72 bytes in a saved character's `.SWG` (big-endian, word-aligned):

| DAX | SWG | field |
|-----|-----|-------|
| 0x00 | 0x00 | name (length byte + text / C string; monster item names are junk) |
| 0x2E | 0x30 | type (index into the type table) |
| 0x2F-0x31 | 0x32-0x34 | three name words; the name reads word 3, 2, 1 |
| 0x32 | 0x37 | magical plus (charges for wands and necklaces) |
| 0x34 | 0x3A | readied |
| 0x35 | 0x3B | name words hidden until identified (bit 2: word 1, bit 1: word 2) |
| 0x36 | 0x3D | cursed |
| 0x37 | 0x3E | weight (u16) |
| 0x39 | 0x40 | count (arrows, darts) |
| 0x3A | 0x42 | value in steel (u16) |
| 0x3C-0x3E | 0x44-0x46 | effects: a scroll's spell numbers, charges... |

Name words are the item word list in the executable (1 Battle Axe ... 90
"of" ... 111 "+1"): 3c 4d 5a 08 is type 60, words Disruption / of / Mace,
"Mace of Disruption". The third operand of the ECL `LOAD MONSTER`
instruction is the combat icon (`CPICn.DAA` id).

`TREASURE` has eight operands: silver, copper, bronze, platinum, steel,
gems, jewelry, and an `ITEMn.DAX` block (255 none, 128 + n: n random
items). 1 steel = 2 platinum = 5 bronze = 10 copper = 50 silver. Nearly
always it comes right before `COMBAT` and is the loot of that fight. The
outposts open their armoury with `SAVE 1, [7F6C]`, a `TREASURE` naming the
stock, then `COMBAT`; the temple with `SAVE 1, [7EE2]` and `COMBAT`.

## Executable

`game` is a hunk file of 101 code hunks compiled from Pascal. Each unit
starts with its constants, and a `move.l a4,-(sp); movea.l base(pc),a4;
link a5` prologue points A4 at them. `tools/hunk.py` relocates it at
0x10000. `tools/disasm68k.py` disassembles it by recursive descent
(capstone), names routines and annotates A4-relative strings.
