# Champions of Krynn (Amiga) — decompile and Python remake

A personal project to take the 1990 SSI/TSR Gold Box game apart and rebuild
it in Python, so its worst flaws can be fixed.

> The game is **not** in this repository. Put your own copy (the `.zip` of
> ADF images, or the `.adf` files) in `krynn/original/`. `.gitignore` keeps
> it, and everything extracted from it, out of git.

## What works now

Every change from the original game, the rule choices and the bugs fixed are
listed in [docs/CHANGES.md](docs/CHANGES.md).

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
  view with the original walls. Laid out for 1920x1080: the original art is
  enlarged by whole numbers (3D view 7x, big pictures 5x, combat 2x) so it
  stays crisp, and text, roster and an always-visible automap of the squares
  you have visited are drawn at full resolution. Any window size works
  (letterboxed), F11 for full screen. Also new: mouse support.
* **Overhead tactical combat**: the original's fake-isometric battlefield
  is replaced by a straight top-down grid built from the map around the
  party, or open ground outdoors. It uses the original combat icons and
  tiles and the AD&D rules (initiative, THAC0/AC, damage dice, attacks of
  opportunity, dying at 0 and dead at -10). Monsters and the party take
  their stats from the game's own records. The screen shows how far you can
  move, which squares are threatened, and your hit chance and damage.
  Missile weapons work: bows, crossbows, slings, the kender hoopak, darts
  and javelins, read from each character's items (and from monsters'
  inventories, such as the dark mages' darts). You need range and a clear
  line of sight, you can't shoot with an enemy next to you, dexterity
  helps the shot, and arrows are used up (half are gathered again after a
  victory, along with any thrown darts or javelins).
* **Spells in combat**: the party casts what each character has memorised
  (read from the save) and monster casters use their own spell lists, so a
  Bozak really does throw Lightning Bolts and Stinking Clouds. Press M,
  pick a spell, and aim it with the arrows or the mouse: before you cast,
  the squares it covers are lit and every creature it will hit is
  outlined, with a warning when a Fireball or Stinking Cloud would catch
  your own people. Saving throws, Sleep's hit-dice limit, Hold and Sleep
  victims being slain outright in melee, Charm switching sides, Mirror
  Image, Haste and Slow, Bless and Prayer bonuses, Confusion and Fear all
  work. Tags over each icon show who is asleep, held, charmed and so on.
  Cast spells stay used until the party rests.
* **Saving and loading**: F5 saves into one of ten slots whenever the
  party is free to move (not mid-conversation or mid-fight), F9 loads,
  also after the party falls. A save keeps everything: the script state
  and all the module's flags, position, map and walls, each character's
  record, hit points, experience, items and spells, the journal and the
  automap. Saves are JSON files in `krynn/saves/` (kept out of git; set
  `KRYNN_SAVES` to put them elsewhere).
* **Camp, rest and memorising**: E makes camp, as in the original. Pick
  each caster's spells in Memorise (the slots follow the AD&D tables, the
  cleric's wisdom bonus and, for mages, Krynn's moons: their order's moon
  in high sanction gives two extra spells, waxing one). A night's rest
  heals everyone a little (one hit point per level, not the original's one
  a day) and brings the chosen spells back. Instead of resting over and
  over by hand, "Rest until healed" and "Fix" (the clerics cast their
  cures, then the party rests and repeats) do it in one go and stop if
  the night is interrupted. Where and how often a rest is interrupted
  comes from each map's own camp script, as in the original, checked once
  a night instead of every hour or so. Cast (in camp) uses the spells that
  matter outside a fight: the cures, Raise Dead (elves cannot be raised;
  the chance to survive comes from constitution), Remove Curse, Detect
  Magic and Read Magic.
* **Treasure, items and the armoury**: the loot a fight is set up with is
  handed over after you win, and each item goes to whoever you choose.
  Coins go into one purse the whole party shares (the original made you
  pool and share coins by hand); it pays in steel and makes its own
  change. Items carry their real names from the game's word list, with
  magic hidden until identified ("Mace" turns out to be a Mace of
  Disruption +1). I shows each character's items: readying armour or a
  weapon recalculates AC, THAC0 and damage (the formula reproduces the
  saved party's figures exactly), a bow can stay slung beside a sword,
  potions of healing work and mages scribe spells from scrolls. The
  outposts' armouries buy, sell, identify and take gems and jewelry; the
  temples heal for steel.
* **Training**: the halls (and the travelling trainers) open a training
  screen. The levels, experience tables and level limits are the manual's,
  and each saved character falls exactly on them. Training raises hit
  points, THAC0, saving throws and spell slots, and a mage picks a new
  spell from those open to the Red or White Robes. Unlike the original,
  experience beyond the next level is never lost, and a new level never
  gives fewer than half the hit die's points.
* **Magic items in combat**: I in a fight lists the character's potions,
  wands, the necklace of missiles and scrolls, and each is aimed like a
  spell, with the same preview. Wands spend charges, potions are drunk,
  a scroll loses each spell as it is read (only by its own robe). Party
  members on auto drink healing potions when badly hurt. Readied weapons
  keep their special powers: the Dragonlance doubles its damage against
  dragons, the Mace of Disruption against undead, the long sword +4 vs
  reptiles hits draconians harder, and the gauntlets of ogre power and
  girdle of giant strength raise a weak character's strength bonuses.
* **The gods and the knightly orders**: each cleric's god grants its
  special spells in their own memorise slot (Paladine: Protection from
  Evil 10', Majere: Silence, Kiri-Jolith: Detect Magic, Mishakal: Bless,
  Remove Curse, Charm Person, Sirrion: Burning Hands, Shinare: Charm
  Person) and its powers (Kiri-Jolith and, for dwarves, Reorx: +1 to hit;
  Mishakal: one more die on every healing spell). At a hall, K lets a
  knight petition the Knights of the Sword or the Rose, with the
  manual's experience and ability requirements. Fighters and knights from
  7th level and rangers from 8th strike three times every two rounds.
* **Morale**: monsters no longer fight to the last goblin. When half their
  side is down, or one is badly hurt, each rolls against its morale (better
  for tougher monsters) and may break and run for the edge of the field,
  taking free attacks as it goes. Runaways give no experience. Undead and
  other mindless things never run, a lone monster fights to the end, and a
  monster with no way out turns and fights.
* **The journal is in the game**: when the story says "you record it in
  journal entry 51" or "you hear tavern tale 12", that page of the manual
  opens on screen, maps and pictures included. Every entry the party finds
  is kept in the Journal (J, or the button bottom right), with separate
  Journal and Tavern tabs. The text comes from your own scanned manual:
  `python3 tools/journal.py original/<manual>.pdf` (needs `brew install
  poppler tesseract` and `pip3 install pillow numpy`). It reads the 88
  journal entries and 57 tavern tales by OCR, crops the maps, and writes
  `extracted/journal/` (kept out of git). Fix any OCR slip in
  `journal.json`; its `fixes` section survives a re-run.
* **Replaceable combat blocks**: every wall, door, floor and obstacle has a
  fixed id (`W1-01-03`, `D2-13-07`, `O-WILD-06`...). Drop
  `remake/art/blocks/<ID>.png` in to redraw one; see
  [remake/art/README.md](remake/art/README.md) and the list in
  [remake/art/BLOCKS.md](remake/art/BLOCKS.md).

## What does not work yet

The parts of the original engine that live in `game` rather than in the
scripts are still to be rebuilt:

* character creation and the character sheet (the party is loaded from the
  save disk)
* the vault (banking)
* sound and music

## Play

```sh
pip3 install pygame-ce
python3 remake/krynn.py            # finds krynn/original/*.zip by itself
python3 remake/krynn.py --size 1600x900    # or --fullscreen
python3 remake/krynn.py --load A           # carry on from saved game A
```

| key | action |
|-----|--------|
| ↑ / W | forward (overland: north) |
| ← → / A D | turn (overland: west/east) |
| ↓ / S | turn around (overland: south) |
| L | search/look |
| RETURN / SPACE, or a letter | choose a menu option (mouse works too) |
| J | the journal (entries and tavern tales found so far) |
| I | items: ready, give, drop, use (potions, scrolls to scribe) |
| E | make camp: rest, rest until healed, fix (heal with spells), memorise spells, save |
| F5 / F9 | save / load (ten slots, A to J) |
| F11 | full screen |
| ESC | quit |

In combat:

| key | action |
|-----|--------|
| arrows / WASD, Q E Z C (or numpad) | move, diagonals with Q E Z C |
| move into an enemy, or click it | attack |
| click a lit square | walk there |
| T, RETURN | pick a target, attack it |
| F, or click a distant enemy | shoot it (the dashed line shows a clear shot) |
| M | cast a spell: choose it (arrows + RETURN, or its number), aim (arrows or mouse), RETURN or click to cast, ESC to go back |
| B | bandage a dying friend next to you |
| SPACE / G | end the turn |
| U / shift+U | the computer plays this character / the whole party (again to stop) |
| L | leave: flee from the edge of the field |
| V | zoom in 2x around the active character |

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
cok/            format library: adf, dax, compress, gfx, ilbm, geo, view3d, ecl, items, blocks, gamefiles, png
tools/          extract.py, adf.py, hunk.py, disasm68k.py (+ labels68k.txt), list_blocks.py, journal.py
remake/         krynn.py (pygame), play_text.py, fonts/, art/ (replacement block art)
remake/kroc/    vm, world, app, combat (rules), spells, encounter, combat_screen, art, journal,
                savegame, save_screen, magic (spell slots, moons), camp_screen, inventory,
                training, hall_screen
docs/           FORMATS.md
tests/          run_tests.py
```
