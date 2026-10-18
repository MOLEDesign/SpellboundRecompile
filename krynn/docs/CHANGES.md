# Changes from the original

What the remake does differently from the 1990 Amiga game, and why. It has
three parts:

* **Improvements**: deliberate changes to fix the original's flaws.
* **Rule choices**: where the remake had to pick a rule or a number. The
  table says where to change each one.
* **Bugs fixed**: problems found and fixed while rebuilding the engine.

The story, the maps, the event scripts, the monsters and the items are all
the original's: the remake reads them from your own disks.

## Improvements

### Presentation

| Original | Remake |
|----------|--------|
| 320x200 screen, everything at one size | Laid out for 1920x1080. Art is enlarged by whole numbers (3D view 7x, big pictures 5x, combat 2x) so it stays crisp, and text is drawn at full resolution. Any window size works (letterboxed); F11 for full screen. |
| | Mouse works in menus, combat and every screen. |
| | An automap of the squares you have visited is always on screen. |
| Journal entries and tavern tales printed in the manual ("read journal entry 51") | The entry opens on screen when the story mentions it, maps and pictures included. Every entry found is kept in a Journal (J), with Journal and Tavern tabs. |

### Combat

| Original | Remake |
|----------|--------|
| A fake isometric battlefield: a skewed grid drawn from the same tiles | A straight top-down grid built from the map around the party, or open ground outdoors, using the original icons and tiles. |
| Hard to tell how far you can move or what is threatened | Squares you can reach are lit, squares enemies threaten are marked, and the panel shows your hit chance and damage against the target. |
| Area spells aimed blind | Before you cast, the squares a spell covers are lit, every creature it will hit is outlined, and you are warned if friends are inside a Fireball or Stinking Cloud. |
| Swapping between bow and sword by hand | A bow stays slung beside a melee weapon; F shoots, moving into an enemy strikes. |
| Arrows spent | After a victory the party recovers half its arrows and quarrels and every thrown dart and javelin. |
| Monsters fight to the last goblin | Monsters check morale and may break and run (see Rule choices). |
| Playing every character every round | U hands a character to the computer; shift+U the whole party. |
| Walls drawn only from the original art | Every wall, door, floor and obstacle has a fixed id (`W1-01-03`, `O-WILD-06`...). Put `remake/art/blocks/<ID>.png` in place to redraw one ([art/README.md](../remake/art/README.md), [BLOCKS.md](../remake/art/BLOCKS.md)). |

### Camping and spells

| Original | Remake |
|----------|--------|
| Slow natural healing: many rests, each a chance of being ambushed | A night heals 1 hit point per character level. "Rest until healed" rests as many nights as needed in one go and stops if a night is interrupted. |
| Healing the party meant casting each cure spell by hand, resting, and repeating | Fix: the clerics cast all their cures on whoever is most hurt, then the party rests and repeats until everyone is whole. |
| Interruptions checked repeatedly through a rest | Checked once a night, with each map's own chance (see Rule choices). |
| Unclear why a mage has more spells some nights | The memorise screen shows every slot by level, the moon bonus, and the phase of each moon. |

### Money and items

| Original | Remake |
|----------|--------|
| Coins carried by each character in seven kinds; pooling and sharing by hand | One purse for the whole party. It pays in steel and makes its own change, using the cheapest coins first. |
| Treasure split by hand through Take / Pool / Share menus | Coins go straight into the purse; you choose who carries each item, or press A to take all. |
| Selling gems and jewelry one at a time | J sells all gems and jewelry in one go. |

### Saving

| Original | Remake |
|----------|--------|
| Saving only from the camp menu, to a save disk | F5 saves into one of ten slots (A-J) whenever the party is free to move; F9 loads, also after the party falls. `krynn.py --load A` starts from a save. Saves are written so a crash cannot leave a half-written file. |

## Rule choices

The original engine's code for these has not been fully decoded yet, so the
remake follows the manual and AD&D. Each one is in a single place and easy
to change.

| What | Remake's rule | Where |
|------|---------------|-------|
| Natural healing | 1 HP per character level per 8-hour night | `World.night` in `remake/kroc/world.py` |
| Rest interruptions | Each map's `precamp` script sets the chance (`7ED3`); rolled once per night | `World.camp` in `world.py` |
| Spell slots | AD&D tables, the cleric's wisdom bonus, the moons (manual p.16). This reproduces the saved party's spells exactly. | `remake/kroc/magic.py` |
| Moons | Solinari 36 days, Lunitari 28, Nuitari 8, all full on day 1. Waxing: +1 spell. High sanction: +2 spells, +1 to saves, +1 level (level 6+, INT 15+). Low sanction: -1 save, -1 level. | `magic.MOONS`, `magic.PHASE_EFFECT` |
| Spell effects | AD&D spell descriptions: ranges, areas, durations, saves | `TABLE` in `remake/kroc/spells.py` |
| Sleep, Hold and coup de grace | Sleep affects 4 hit dice or fewer; a sleeping or held victim struck in melee dies | `spells.py`, `Battle.swing` in `combat.py` |
| Morale | Rolled the first time half a monster's side is down, and the first time it falls below a third of its HP. Morale is 40 + 6 per hit die (max 95). Undead and golems never run; a lone monster never runs; a cornered one fights on. Monsters that run give no experience. | `encounter.morale`, `Battle.check_morale` |
| Saving throws (party) | AD&D tables by class and level; paladins +2 | `Character.save_spell` in `world.py` |
| Coin values | 1 steel = 2 platinum = 5 bronze = 10 copper = 50 silver (manual p.4) | `COIN_VALUE` in `world.py` |
| Selling | Half the item's value | `ShopView.sell` in `remake/kroc/inventory.py` |
| Identifying | 100 steel (the original's price) | `IDENTIFY_PRICE` in `inventory.py` |
| Gems and jewelry | A gem is worth 10-500 steel, jewelry 300-1800 | `ShopView.sell_gems` |
| Temple healing | 5 steel per hit point | `TempleView.PER_HP` |
| Random treasure (`TREASURE` item block 128 + n) | n items drawn from all item records on the disks | `World.treasure` |
| Potions of healing | Healing 2d4+2, Extra Healing 3d8+3 | `ItemsView.use` |

## Bugs fixed

These were found while rebuilding the engine. Each one changes what you see
in play.

| Problem | Fix |
|---------|-----|
| The scripts could not tell which room or area of a map the party was in (`C04F`, the GEO square flags, always read 0). Area events never fired: the guards at Throtl's gate were skipped and the party walked straight in. | `C04F` returns the party's square flags. The gate encounter and the other room events now happen as written. |
| Readying different weapons or armour changed nothing: AC, THAC0 and damage were the save disk's figures | They are worked out from the readied items. The formula gives the saved party's figures exactly, and changing equipment now counts. |
| Experience started at 0 | Read from the character record (offset 0x11E). |
| `TREASURE` handed out loot before the fight it belongs to | The loot is held until the fight is won, then handed out. |
| Shops and temples opened an empty fight | The scripts open them through `COMBAT` with a flag set (`7F6C` shop, `7EE2` temple); the remake opens the armoury or temple instead. |
| Saved items read a plus of +104 | That byte is leftover memory; the real plus is two bytes later (the SWG records are word-aligned). |
| Area spells were blocked by creatures standing in the way | Only walls block a spell's line of sight. |
| A creature asleep or held could still make free attacks and stop archers shooting | Only creatures able to act count as a threat. |
| The combat log printed "shoots at BOZAK. and misses" | Fixed wording. |

How the data formats were decoded, including these offsets, is in
[FORMATS.md](FORMATS.md).

## Not yet rebuilt

* training and levelling up
* wands, potions and scrolls used in combat
* the vault (banking at the outposts)
* casting spells outside combat (other than Fix's healing)
* the gods' bonus spells for clerics
* character creation and the character sheet (the party comes from the save disk)
* sound and music
