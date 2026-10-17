# Spellbound 128K – technical notes

All addresses are hex. "bank N" means 128K RAM page N mapped at C000.

## The tape

| block | content                                                          |
|-------|------------------------------------------------------------------|
| 0/1   | BASIC loader `SPELL128`                                          |
| 2/3   | `SPELL$` loading screen, 6912 bytes                              |
| 4–11  | four 16K blocks loaded to 8000 and copied to banks 1, 3, 4, 6    |
| 12/13 | main program, 39295 bytes at 6680 (26240) – runs to FFFF          |

The loader:

```basic
10 CLEAR VAL "26200": LET ad=26627 ...
20 LOAD "" SCREEN$
30 GO SUB 100        : REM pokes a bank-copy stub at 26210
40-70 for A in 1,3,4,6: LOAD "" CODE, RANDOMIZE USR 26210
80 LOAD "" CODE
90 RANDOMIZE USR ad  : REM 26627 = 6803
```

The stub at 26210: `DI; LD A,bank; LD BC,7FFD; OUT (C),A; LD HL,8000; LD DE,C000;
LD BC,4000; LDIR; LD A,10h; OUT (C),A; EI; RET`.

## Memory map

| range        | content                                                        |
|--------------|----------------------------------------------------------------|
| 4000–5AFF    | screen (bank 5)                                                 |
| 5C00–5CB5    | system variables. The game uses LAST_K and FLAGS, plus its own variables, e.g. 5C95 = current room |
| 5D05–5D64    | 3×32-byte sprite work buffer                                     |
| 5E00–60DF    | collision map for the current room                              |
| 6200–64FF    | game variables (stack grows down from 6680)                     |
| 6680–67FF    | table of 192 screen-line addresses                              |
| 6803         | entry point                                                     |
| A768         | IM 2 interrupt handler                                          |
| B700–BAFF    | font, 128 glyphs (00–1F are window-frame pieces)                |
| BB00–BDDF    | 92 scenery tiles, 8×8                                           |
| C544         | decoration table (4 bytes per entry: w, h, data pointer)        |
| F9F4 / FCF4  | Magic Knight graphics / mask, 8 frames × 96 bytes               |
| FFF4 / FFFF  | IM 2 trampoline: `JP A768` / `JR` (planted in every bank)       |
| bank 3       | room layouts (C000, 57 × 160) and block definitions (E3A0)      |
| bank 4       | AY music driver (C000 init, C003 stop, C006 play) and tune data  |
| bank 7       | shadow screen + clean copy of the room (E000+) for sprite restore |
| banks 1, 6   | further game data – not yet decoded                              |

## Hardware use

* **Interrupts**: IM 2 with I pointing into the ROM, where the bytes are FF.
  The vector is FFFF, which holds `JR`; the offset comes from ROM address 0000
  (F3), giving a jump back to FFF4: `JP A768`. The replacement ROM only has to
  provide FF bytes and F3 at 0000.
* **ROM calls**: only `KEYBOARD` (02BF), called from the interrupt handler.
  It's emulated in `hle_keyboard()` in `src/spectrum.c`: it sets LAST_K (5C08)
  and FLAGS bit 5, with auto-repeat via REPDEL/REPPER.
* **Paging**: `page_bank` (6A57) writes `bank | 10h | (64BF)` to 7FFD; bit 3
  from 64BF selects the shadow screen.
* **Sound**: AY via FFFD/BFFD from the bank 4 driver, called each interrupt.

## Rooms

* `enter_room` (6FA6), A = room number 0–56.
* Layout: bank 3, `C000 + room*160`. That's 16×10 bytes, one block index
  per 16×16 cell, drawn from screen row 5 (40A0).
* Block: bank 3, `E3A0 + block*8` =
  `attr, collision byte, solidity flags, 0, tile TL, tile TR, tile BL, tile BR`.
* Tiles: `BB00 + tile*8`.
* Then a per-room list (pointer found through the table at 9C1F) of
  decorations and objects. Each entry is a decoration index, position and
  attribute, with codes FB–FF as commands. A decoration is drawn by
  `draw_decoration` (7409): A = index into the C544 table, L = column,
  H = row, C = mode (0 normal, 1 mirrored, 2 upside-down, 3 both).

## Sprites

Moving sprites are 24×32 pixels and use a save/mask/restore scheme:
`sprite_save_background` (A4FF) copies the clean background for the sprite
area out of bank 7 into the buffer at 5D05. `sprite_mask_knight` (A569)
ANDs in the mask and ORs in the graphics. `sprite_put_buffer` (A5A2)
writes the result to the screen, using the line table at 6680.

## Approach

1. `tools/tap_extract.py` rebuilds the memory exactly as the loader leaves it.
2. A from-scratch Z80 core is checked against ZEXDOC/ZEXALL. It runs the
   original code; anything that would need the ROM is trapped and emulated
   in C.
3. Recorded coverage (`--coverage`) feeds the disassembler, so code reached
   only through jump tables is still found. `tools/labels.txt` names the
   routines identified so far.
4. Assets the game builds at run time (rooms, mirrored decorations) are
   captured by calling the game's own routines in the emulator. This is
   exact without decoding every packed format by hand.

## Next steps toward a full rewrite

* Decode the per-room object/character lists (9C1F) and the character
  sprites so that a map editor or a high-level C rewrite becomes possible.
* Decode banks 1 and 6 and the text/command tables – the menu system,
  characters' moods and the spell list.
* Gradually replace routines with C equivalents (rendering first), checking
  each against the original by comparing frames in headless mode.
