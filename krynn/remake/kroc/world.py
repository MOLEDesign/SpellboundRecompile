"""Game state shared by the VM and the front ends (no pygame here)."""

from cok import gfx, view3d
from cok.dax import Container
from cok.gamefiles import GameFiles
from cok.geo import GeoMap

from cok.items import Item

from .vm import VM, IN_DUNGEON

# coins, as the TREASURE instruction lists them, and their worth in steel
COINS = ('silver', 'copper', 'bronze', 'platinum', 'steel', 'gems', 'jewelry')
COIN_VALUE = {'silver': 1 / 50, 'copper': 1 / 10, 'bronze': 1 / 5, 'platinum': 1 / 2, 'steel': 1}
SHOP_FLAG, TEMPLE_FLAG = 0x7F6C, 0x7EE2      # set before COMBAT: a shop / a temple, not a fight
NIGHT = 8 * 60                  # a night's rest, in minutes
REST_INTERVAL, REST_CHANCE = 0x7ED2, 0x7ED3     # set by the precamp script
NEW_GAME_BLOCK = 0x24       # "At the Inn of the Last Home in Solace..."
OVERLAND_X, OVERLAND_Y = 0x4BC3, 0x4BC4
CANCEL_MOVE = 0x7EC9
OVERLAND_W, OVERLAND_H = 38, 15     # the overland picture in 8x8 cells


def clock_text(minutes):
    day, m = divmod(minutes, 24 * 60)
    return 'Day %d, %02d:%02d' % (day + 1, m // 60, m % 60)


class Files:
    """Containers of the game, opened lazily. Area 1 is disk 2, area 2 disk 3."""

    def __init__(self, source=None):
        self.gf = GameFiles(source)
        self._c = {}

    def container(self, name):
        name = name.lower()
        if name not in self._c:
            self._c[name] = Container(self.gf.read(name), name) if name in self.gf else None
        return self._c[name]

    def find(self, prefix, block_id, exts=('.dax', '.daa'), prefer=None):
        """Entry block_id from prefix1/prefix2 (e.g. ECL1.DAX/ECL2.DAX)."""
        areas = ('1', '2', '0', '')
        if prefer:
            areas = (prefer,) + tuple(a for a in areas if a != prefer)
        for area in areas:
            for ext in exts:
                c = self.container(prefix + area + ext)
                if c is not None and block_id in c:
                    return c, area
        return None, None

    def ecl(self, block_id):
        c, area = self.find('ecl', block_id)
        if c is None:
            raise KeyError('ECL block %02X not found' % block_id)
        self.area = area            # monsters and icons come from the same disk
        return c.get(block_id)

    def monster(self, mid, area=None):
        """Raw monster record (MONnCHA.DAX) or None."""
        c, _ = self.find('mon', mid, ('cha.dax',), prefer=area)
        return c.get(mid) if c is not None else None

    def combat_icon(self, mid, area=None):
        """(ready, attack) pictures of a monster's combat icon."""
        c, _ = self.find('cpic', mid, ('.daa',), prefer=area)
        if c is None:
            return None, None
        ready = gfx.decode_block(c.get(mid))
        attack = gfx.decode_block(c.get(mid | 0x80)) if (mid | 0x80) in c else ready
        return ready, attack

    def item_types(self):
        if not hasattr(self, '_types'):
            from cok.items import load_types
            self._types = load_types(self.gf.read('items')) if 'items' in self.gf else {}
        return self._types

    def monster_items(self, mid, area=None):
        from cok.items import parse_dax_items
        c, _ = self.find('mon', mid, ('itm.dax',), prefer=area)
        return parse_dax_items(c.get(mid), monster=True) if c is not None else []

    def item_words(self):
        if not hasattr(self, '_words'):
            from cok.items import load_words
            self._words = load_words(self.gf.read('game')) if 'game' in self.gf else {}
        return self._words

    def item_block(self, bid):
        """The items of ITEMn.DAX block bid (a treasure or a shop's stock)."""
        from cok.items import parse_dax_items
        c, _ = self.find('item', bid, ('.dax',))
        return parse_dax_items(c.get(bid)) if c is not None else []

    def all_items(self):
        """Every item record on the disks: the pool random treasure is drawn from."""
        out = []
        for name in ('item1.dax', 'item2.dax'):
            c = self.container(name)
            for bid in (c.ids() if c is not None else []):
                out.extend(self.item_block(bid))
        return out

    def tiles(self, name):
        """Combat tile set (DUNGCOM/WILDCOM/RANDCOM) as a Picture."""
        c = self.container(name + '.daa')
        return gfx.decode_block(c.get(c.ids()[0])) if c is not None else None

    def picture(self, pid):
        """Picture by ECL id: big pictures, then the animated 88x88 pics."""
        for prefix in ('bigpic', 'pic', 'cpic'):
            c, _ = self.find(prefix, pid, ('.daa',))
            if c is not None:
                return gfx.decode_anim(c.get(pid)) if c.kind == 'anim' else gfx.decode_block(c.get(pid))
        return None

    def sprite(self, sid):
        c, _ = self.find('sprit', sid, ('.daa',))
        return gfx.decode_anim(c.get(sid)) if c is not None else None


def _s8(b):
    return b - 256 if b > 127 else b


class Character:
    """A party member, from a CHRDATAn.SAV record (426 bytes).

    Offsets worked out from the save disk's party: 0x00 name, 0x10 six stat
    pairs (current, maximum), 0x1C exceptional strength, 0x5B race, 0x5C class,
    0x5A 60-THAC0 before bonuses, 0x64 maximum HP, 0x141-0x14B combat icon (head, body, slot, size, colours),
    0x19B 60-THAC0, 0x19C 60-AC, 0x1A0/0x1A2 weapon dice, 0x1A5 damage bonus,
    0x1A8 current HP, 0x1A9 movement.
    """
    STATS = ('STR', 'INT', 'WIS', 'DEX', 'CON', 'CHA')

    def __init__(self, name, raw=b'', items=()):
        self.name = name
        self.raw = raw
        self.items = list(items)          # cok.items.Item (from the .SWG file)
        self.dead = False
        r = raw if len(raw) >= 0x1AA else bytes(0x1AA)
        self.base_thac0 = 60 - r[0x5A] if r[0x5A] else 20     # without strength bonuses
        self.stats = {s: r[16 + 2 * k] for k, s in enumerate(self.STATS)}
        self.hp_max = r[0x64] or 8
        self.hp = _s8(r[0x1A8]) if raw else self.hp_max
        self.thac0 = 60 - r[0x19B] if r[0x19B] else 20
        self.ac = 60 - r[0x19C] if r[0x19C] else 10
        self.weapon = (r[0x1A0] or 1, r[0x1A2] or 4, _s8(r[0x1A5]))
        self.move = r[0x1A9] or 12
        self.icon = dict(head=r[0x141], body=r[0x142], size=r[0x144] or 2, colours=bytes(r[0x146:0x14C]))
        # 0x1E-0x59 memorised spells (1-94; higher numbers are not spells); 0xFE-0x105
        # levels: cleric, druid, fighter, paladin, ranger, magic-user, thief, knight
        self.memorised = [x for x in r[0x1E:0x5A] if 1 <= x <= 94]   # chosen to memorise
        self.spells = list(self.memorised)        # in memory now: used ones return on a rest
        self.book = [i for i in range(1, 95) if r[0x65 + i]]       # grimoire / prayer list
        self.levels = dict(zip(self.CLASSES, r[0xFE:0x106]))
        self.experience = int.from_bytes(r[0x11E:0x122], 'big')
        self.spell_picks = 0              # new grimoire spells owed after training
        # what strength (and race, items' quirks...) adds, worked out once from the
        # saved figures and the items readied at the time, so that readying other
        # weapons and armour gives the right AC, THAC0 and damage
        self.hit_bonus = None
        self.dmg_bonus = None

    def gain(self, xp):
        """Experience earned: a multi-class character shares it between the classes."""
        from .training import share
        self.experience += share(self, xp)

    def calibrate(self, types):
        from cok import items as I
        it, t = I.melee_weapon(self.items, types)
        plus = it.plus if it else 0
        self.hit_bonus = self.base_thac0 - self.thac0 - plus
        base = t.dice[2] if t else 0
        self.dmg_bonus = self.weapon[2] - base - plus

    def refresh(self, types, words=None):
        """AC, THAC0 and weapon damage from the readied items."""
        from cok import items as I
        if self.hit_bonus is None:
            self.calibrate(types)
        self.ac = I.armour_class(self.items, types, self.stats.get('DEX', 10), words)
        from .magic_items import strength_items
        it, t = I.melee_weapon(self.items, types)
        plus = it.plus if it else 0
        hit, dmg = self.hit_bonus, self.dmg_bonus
        if words:
            least_hit, least_dmg = strength_items(self, words, types)   # gauntlets, girdles
            hit, dmg = max(hit, least_hit or hit), max(dmg, least_dmg or dmg)
        self.thac0 = self.base_thac0 - hit - plus
        if t is None:
            self.weapon = (1, 2, dmg)                         # fists
        else:
            n, size, bonus = t.dice
            self.weapon = (n or 1, size or 4, bonus + plus + dmg)

    # --- saving -------------------------------------------------------------------
    def to_dict(self):
        return {'name': self.name, 'raw': self.raw.hex(), 'hp': self.hp, 'dead': self.dead,
                'experience': self.experience, 'memorised': self.memorised, 'spells': self.spells,
                'book': self.book, 'levels': self.levels, 'hp_max': self.hp_max,
                'base_thac0': self.base_thac0, 'spell_picks': self.spell_picks,
                'items': [i.to_list() for i in self.items],
                'bonus': [self.hit_bonus, self.dmg_bonus], 'ac': self.ac, 'thac0': self.thac0,
                'weapon': list(self.weapon)}

    @classmethod
    def from_dict(cls, d):
        from cok.items import Item
        c = cls(d['name'], bytes.fromhex(d['raw']), [Item.from_list(i) for i in d['items']])
        c.hit_bonus, c.dmg_bonus = d.get('bonus', [None, None])
        c.ac, c.thac0 = d.get('ac', c.ac), d.get('thac0', c.thac0)
        c.weapon = tuple(d.get('weapon', c.weapon))
        c.hp, c.dead, c.experience = d['hp'], d['dead'], d['experience']
        c.memorised, c.spells = list(d['memorised']), list(d['spells'])
        c.book = list(d.get('book', c.book))
        c.levels.update(d.get('levels', {}))
        c.hp_max = d.get('hp_max', c.hp_max)
        c.base_thac0 = d.get('base_thac0', c.base_thac0)
        c.spell_picks = d.get('spell_picks', 0)
        return c

    CLASSES = ('cleric', 'druid', 'fighter', 'paladin', 'ranger', 'magic-user', 'thief', 'knight')
    # d20 needed to save against spells, by class and level (AD&D tables)
    SAVE_SPELL = {'cleric': (15, 15, 15, 14, 14, 14, 12, 12, 12, 11),
                  'magic-user': (12, 12, 12, 12, 12, 10, 10, 10, 10, 10),
                  'thief': (15, 15, 15, 15, 13, 13, 13, 13, 11, 11),
                  'fighter': (17, 17, 16, 16, 14, 14, 13, 13, 11, 11)}

    @property
    def top_level(self):
        return max(self.levels.values()) or 1

    @property
    def save_spell(self):
        best = 17
        for cls, lv in self.levels.items():
            if lv:
                table = self.SAVE_SPELL.get(cls, self.SAVE_SPELL['fighter'])
                n = table[min(lv, len(table)) - 1]
                if cls == 'paladin':
                    n -= 2
                best = min(best, n)
        return best


class World:
    def __init__(self, files=None, log=None):
        self.files = files or Files()
        self.log = log or (lambda s: None)
        self.vm = VM(self)
        self.x = self.y = 0
        self.facing = 0
        self.geo = None
        self.geo_id = None
        self.slots = None
        self.monsters = []
        self.encounter_sprite = None
        self.party = self.load_party()
        self.selected = 0
        self.clock = 0
        self.minutes = 8 * 60        # game time: day 0, eight in the morning
        self.moved = False
        self.journal_found = []      # (kind, n) of journal entries / tavern tales heard
        self.wall_loads = []         # LOAD WALLS calls since the wall set changed (for saves)
        self.purse = dict.fromkeys(COINS, 0)    # the party's money, shared
        self.shop_stock = []         # items of the last TREASURE seen in a shop

    # --- party (placeholder until character creation is rebuilt) -------------
    def load_party(self):
        from cok.items import parse_swg
        party = []
        for n in range(1, 7):
            name = 'save/chrdata%d.sav' % n
            if name in self.files.gf:
                raw = self.files.gf.read(name)
                swg = 'save/chrdata%d.swg' % n
                its = parse_swg(self.files.gf.read(swg)) if swg in self.files.gf else []
                party.append(Character(raw[:16].split(b'\0')[0].decode('latin-1'), raw, its))
        types = self.files.item_types()
        for c in party:
            c.calibrate(types)
        return party or [Character('HERO')]

    def monster_name(self, mid):
        d = self.files.monster(mid, getattr(self.files, 'area', None))
        return d[1:1 + d[0]].decode('latin-1') if d else 'MONSTER %d' % mid

    def party_names(self):
        return [c.name for c in self.party]

    def selected_name(self):
        return self.party[self.selected].name if self.party else ''

    def select_character(self, n):
        n &= 0x7F
        if 0 <= n < len(self.party):
            self.selected = n

    def character_value(self, offset):
        return None

    def add_experience(self, who, amount):
        for c in self.party:
            if not c.dead:
                c.gain(amount)
        self.log('The party gains %d experience.' % amount)

    # --- money and treasure -----------------------------------------------------
    def wealth(self):
        """The purse's coins in steel pieces."""
        return int(sum(self.purse[c] * v for c, v in COIN_VALUE.items()))

    def pay(self, steel):
        """Spend coins worth `steel`, cheapest coins first; False if too poor."""
        if steel > self.wealth():
            return False
        need = float(steel)
        for c in ('silver', 'copper', 'bronze', 'platinum', 'steel'):
            if need <= 0:
                break
            take = min(self.purse[c], int(-(-need // COIN_VALUE[c])))
            self.purse[c] -= take
            need -= take * COIN_VALUE[c]
        if need < 0:                                  # change, in steel and silver
            self.purse['steel'] += int(-need)
            self.purse['silver'] += int(round((-need - int(-need)) * 50))
        return True

    def treasure(self, args):
        """TREASURE silver, copper, bronze, platinum, steel, gems, jewelry, item block.
        Coins go straight into the party's purse; returns (coins found, items).
        Item block 255 is none, 128 + n is n items picked at random."""
        found = {c: n for c, n in zip(COINS, args[:7]) if n}
        bid = args[7] if len(args) > 7 else 255
        if bid == 255:
            items = []
        elif bid >= 128:
            pool = [i for i in self.files.all_items() if i.value]
            items = [self.vm.rng.choice(pool) for _ in range(bid - 128)] if pool else []
            items = [Item.from_list(i.to_list()) for i in items]      # copies
        else:
            items = self.files.item_block(bid)
        if self.vm.get(SHOP_FLAG) == 1:
            self.shop_stock = items                   # the next COMBAT opens the shop
            return {}, []
        for c, n in found.items():
            self.purse[c] += n
        return found, items

    def set_loot(self, args):
        """TREASURE just before COMBAT: a shop's stock, or what the fight will yield."""
        if self.vm.get(SHOP_FLAG) == 1:
            self.treasure(args)
            self.loot = None
        else:
            self.loot = args

    def take_loot(self):
        loot, self.loot = getattr(self, 'loot', None), None
        return loot

    def refresh_party(self):
        types, words = self.files.item_types(), self.files.item_words()
        for c in self.party:
            c.refresh(types, words)

    @property
    def day(self):
        return self.minutes // (24 * 60)

    def rest(self):
        """A night at an inn: the living recover all their hit points and spells."""
        self.minutes += NIGHT
        for c in self.party:
            if not c.dead:
                c.hp = c.hp_max
                self.rememorise(c)

    def rememorise(self, c):
        """After a full rest: the chosen spells are back in memory (as many as fit)."""
        from . import magic
        kept, dropped = magic.fit(c, c.memorised, self.day)
        c.spells = kept
        if dropped and any(magic.SPELLS[s].cls == magic.MAGE for s in dropped):
            self.log('%s cannot hold every chosen spell under the moons tonight.' % c.name)
        return dropped

    def night(self):
        """Eight hours of rest in camp: some hit points back, spells memorised."""
        self.minutes += NIGHT
        for c in self.party:
            if c.dead:
                continue
            if c.hp < c.hp_max:
                c.hp = min(c.hp_max, max(c.hp, 0) + c.top_level)
            self.rememorise(c)

    def party_hurt(self):
        return any(not c.dead and c.hp < c.hp_max for c in self.party)

    def spells_missing(self):
        from . import magic
        return any(not c.dead and sorted(c.spells) != sorted(magic.fit(c, c.memorised, self.day)[0])
                   for c in self.party)

    def cast_cures(self):
        """Clerics use their healing spells on whoever is most hurt (the camp's Fix).
        Returns the lines to show."""
        from .spells import SPELLS
        from .combat import roll
        out = []
        cures = (63, 57, 3)                   # critical, serious, light: biggest first
        for healer in self.party:
            if healer.dead or healer.hp <= 0:
                continue
            for sid in cures:
                while sid in healer.spells:
                    hurt = [c for c in self.party if not c.dead and c.hp < c.hp_max]
                    if not hurt:
                        return out
                    t = max(hurt, key=lambda c: c.hp_max - c.hp)
                    n, size, plus = {3: (1, 8, 0), 57: (2, 8, 1), 63: (3, 8, 3)}[sid]
                    amount = roll(self.vm.rng, n, size, plus)
                    t.hp = min(t.hp_max, max(t.hp, 0) + amount)
                    healer.spells.remove(sid)
                    out.append('%s casts %s on %s: +%d.' % (healer.name, SPELLS[sid].name, t.name, amount))
        return out

    def camp(self, mode='rest'):
        """Generator: make camp and rest. mode 'rest' = one night, 'heal' = until
        everyone is healed and has their spells, 'fix' = the same, the clerics
        casting their healing spells first each time.

        The module's precamp script sets the chance (7ED3, percent) that a
        night is interrupted and whether it is checked at all (7ED2); 0 means
        a safe place. An interrupted rest runs the campint script (an
        ambush, a visitor, "you cannot rest here"...)."""
        yield ('print', 'The party makes camp...\n', True)
        self.vm.set(REST_INTERVAL, 0)
        self.vm.set(REST_CHANCE, 0)
        yield from self.vm.run('precamp')
        if self.vm.new_ecl is not None:
            yield from self._settle()
            return
        interval, chance = self.vm.get(REST_INTERVAL), self.vm.get(REST_CHANCE)
        nights = 1 if mode == 'rest' else 30
        for k in range(nights):
            if mode == 'fix':
                for line in self.cast_cures():
                    yield ('print', line + '\n', False)
            if mode != 'rest' and not self.party_hurt() and not self.spells_missing():
                break
            if interval and chance and self.vm.rng.randint(1, 100) <= chance:
                self.minutes += self.vm.rng.randint(1, NIGHT)
                yield ('print', 'The party is disturbed...\n', True)
                yield from self.vm.run('campint')
                yield from self._settle()
                return
            self.night()
            yield ('print', 'The party rests through the night. %s.\n' % clock_text(self.minutes), False)
        if mode == 'fix':
            for line in self.cast_cures():
                yield ('print', line + '\n', False)
        if self.party_hurt():
            if mode != 'rest':
                yield ('print', 'Some wounds still need time.\n', False)
        else:
            yield ('print', 'Everyone is fit and ready.\n', False)

    def advance_clock(self, n):
        self.clock += n

    # --- map ------------------------------------------------------------------
    @property
    def in_dungeon(self):
        return bool(self.vm.get(IN_DUNGEON))

    def set_position(self, x=None, y=None, facing=None):
        if x is not None:
            self.x = x & 15
        if y is not None:
            self.y = y & 15
        if facing is not None:
            self.facing = facing
        self.moved = True

    def load_map(self, geo_id):
        c, area = self.files.find('geo', geo_id, ('.dax',))
        if c is None:
            self.log('GEO block %02X missing' % geo_id)
            return
        self.geo = GeoMap(c.get(geo_id), geo_id)
        self.geo_id = geo_id
        self.map_area = area

    def load_walls(self, a, b, c):
        area = getattr(self, 'map_area', '1') or '1'
        wd = self.files.container('walldef%s.dax' % area)
        sym = self.files.container('8x8d%s.daa' % area)
        common = gfx.decode_block(self.files.container('8x8d0.daa').get(0xCB)).frames
        if self.slots is None or self.slots.walldef is not wd:
            self.slots = view3d.WallSlots(wd, sym, common)
            self.wall_loads = []
        if all(w not in (0xFF, 0x7F) for w in (a, b, c)):
            self.wall_loads = []        # all three slots replaced: earlier loads no longer matter
        self.wall_loads.append((a, b, c))
        for slot, wid in ((1, a), (2, b), (3, c)):
            if wid not in (0xFF, 0x7F) and wid in wd:
                self.slots.load(slot, wid)

    def encounter_distance(self):
        """Open squares ahead (0-2), as the engine measures encounter range."""
        if not self.in_dungeon or not self.geo:
            return 2
        from cok.geo import DX, DY
        x, y, n = self.x, self.y, 0
        while n < 2 and not self.geo.wall(x, y, self.facing):
            n += 1
            x, y = x + DX[self.facing], y + DY[self.facing]
        return n

    def square_flags(self):
        if not self.in_dungeon or not self.geo:
            return 0
        return self.geo.squares[self.y][self.x].flags

    def wall_ahead(self, direction=None):
        d = self.facing if direction is None else direction
        return self.geo.wall(self.x, self.y, d) if self.geo else 0

    def door_state(self, direction=None):
        d = self.facing if direction is None else direction
        return self.geo.door(self.x, self.y, d) if self.geo else 1

    # --- the event loop, as generators -------------------------------------------
    def start(self, block=NEW_GAME_BLOCK):
        """Generator: begin a new game."""
        self.vm.load(block)
        yield from self.vm.run('init')
        yield from self._settle()

    def _settle(self):
        """After a NEWECL: load the new block and run init/run/search until stable."""
        while self.vm.new_ecl is not None:
            nxt = self.vm.new_ecl
            self.vm.load(nxt)
            yield ('block', nxt)
            yield from self.vm.run('init')
            if self.vm.new_ecl is not None:
                continue
            yield from self.vm.run('run')
            if self.vm.new_ecl is not None:
                continue
            yield from self.vm.run('search')

    def step(self, action):
        """Generator: the party did something on the map (move/turn/search)."""
        if action == 'search':
            yield from self.vm.run('search')
            yield from self._settle()
            return
        old = (self.x, self.y, self.vm.get(OVERLAND_X), self.vm.get(OVERLAND_Y))
        if self.in_dungeon and action == 'forward' and self.geo and self.door_state() in (2, 3):
            # locked door: 2 can be picked or bashed, 3 only bashed
            items = ['BASH', 'PICK', 'EXIT'] if self.door_state() == 2 else ['BASH', 'EXIT']
            yield ('print', 'Locked.', True)
            sel = (yield ('menu', items, True)) or 0
            if items[sel] == 'EXIT' or self.vm.rng.random() > (0.35 if items[sel] == 'PICK' else 0.25):
                if items[sel] != 'EXIT':
                    yield ('print', 'The door holds.', True)
                return
            self._forward()
        elif not self.apply_move(action):
            yield ('redraw',)
            return
        self.vm.set(CANCEL_MOVE, 0)
        yield from self.vm.run('run')
        if self.vm.new_ecl is not None:
            yield from self._settle()
            return
        if self.vm.get(CANCEL_MOVE) == 0xFF:
            self.x, self.y = old[0], old[1]
            self.vm.set(OVERLAND_X, old[2])
            self.vm.set(OVERLAND_Y, old[3])
        yield ('redraw',)
        yield from self.vm.run('search')
        yield from self._settle()

    def apply_move(self, action):
        from cok.geo import DX, DY
        if not self.in_dungeon:
            # overland: forward/right/back/left are north/east/south/west
            d = {'forward': 0, 'right': 2, 'back': 4, 'left': 6}[action]
            nx = self.vm.get(OVERLAND_X) + DX[d]
            ny = self.vm.get(OVERLAND_Y) + DY[d]
            if not (0 <= nx < OVERLAND_W and 0 <= ny < OVERLAND_H):
                return False
            self.vm.set(OVERLAND_X, nx)
            self.vm.set(OVERLAND_Y, ny)
            return True
        if action in ('left', 'right', 'back'):
            self.facing = (self.facing + {'left': 6, 'right': 2, 'back': 4}[action]) % 8
            return False
        if action == 'forward':
            # door bits of a wall side: 0 solid, 1 open door, 2 locked, 3 barred
            if self.door_state() != 1:
                return False
            self._forward()
            return True
        return False

    def _forward(self):
        from cok.geo import DX, DY
        self.x = (self.x + DX[self.facing]) & 15
        self.y = (self.y + DY[self.facing]) & 15
