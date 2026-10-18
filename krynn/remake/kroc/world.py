"""Game state shared by the VM and the front ends (no pygame here)."""

from cok import gfx, view3d
from cok.dax import Container
from cok.gamefiles import GameFiles
from cok.geo import GeoMap

from .vm import VM, IN_DUNGEON

NEW_GAME_BLOCK = 0x24       # "At the Inn of the Last Home in Solace..."
OVERLAND_X, OVERLAND_Y = 0x4BC3, 0x4BC4
CANCEL_MOVE = 0x7EC9
OVERLAND_W, OVERLAND_H = 38, 15     # the overland picture in 8x8 cells


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
        return parse_dax_items(c.get(mid)) if c is not None else []

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
        self.experience = 0
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
        self.memorised = [x for x in r[0x1E:0x5A] if 1 <= x <= 94]
        self.spells = list(self.memorised)        # still available until the next rest
        self.levels = dict(zip(self.CLASSES, r[0xFE:0x106]))

    # --- saving -------------------------------------------------------------------
    def to_dict(self):
        return {'name': self.name, 'raw': self.raw.hex(), 'hp': self.hp, 'dead': self.dead,
                'experience': self.experience, 'memorised': self.memorised, 'spells': self.spells,
                'items': [[i.name, i.type, i.ready, i.quantity] for i in self.items]}

    @classmethod
    def from_dict(cls, d):
        from cok.items import Item
        c = cls(d['name'], bytes.fromhex(d['raw']), [Item(*i) for i in d['items']])
        c.hp, c.dead, c.experience = d['hp'], d['dead'], d['experience']
        c.memorised, c.spells = list(d['memorised']), list(d['spells'])
        return c

    CLASSES = ('cleric', 'druid', 'fighter', 'paladin', 'ranger', 'magic-user', 'thief', 'knight')
    # d20 needed to save against spells, by class and level (AD&D tables)
    SAVE_SPELL = {'cleric': (15, 15, 15, 14, 14, 14, 12, 12, 12, 11),
                  'magic-user': (12, 12, 12, 12, 12, 10, 10, 10, 10, 10),
                  'thief': (15, 15, 15, 15, 13, 13, 13, 13, 11, 11),
                  'fighter': (17, 17, 16, 16, 14, 14, 13, 13, 11, 11)}

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
        self.moved = False
        self.journal_found = []      # (kind, n) of journal entries / tavern tales heard
        self.wall_loads = []         # LOAD WALLS calls since the wall set changed (for saves)

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
            c.experience += amount
        self.log('The party gains %d experience.' % amount)

    def rest(self):
        """A night at an inn: the living recover all their hit points."""
        for c in self.party:
            if not c.dead:
                c.hp = c.hp_max
                c.spells = list(c.memorised)

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
