"""Items: the type table (file "items" on disk 1) and item records.

Item type table: u16 header, then 128 records of 16 bytes (index = type)::

    0  slot (0 weapon, 1 shield, 2 armour, 10 ammunition/other ...)
    1  hands needed
    2  damage dice count vs large    3  dice size vs large    4  bonus vs large
    5  half-attacks per round (bows 4 = 2 shots, darts 6 = 3)
    9  damage dice count vs normal   10 dice size vs normal   11 bonus vs normal
    12 range in combat squares (0 = melee only)
    13 classes allowed
    14 flags: 0x01 uses arrows, 0x02 missile weapon, 0x04 melee,
              0x08 ?, 0x10 can be thrown, 0x80 uses quarrels
    15 ?

Weapon type numbers (1 Battle Axe ... 30 Arrow) follow the item name word
list in the executable; the ones combat needs are named in WEAPONS.

Byte 6 is the armour value: (b & 0x7F) - 0x32 for body armour (leather 2
... plate 7, Solamnic plate 10), b & 0x7F for things worn over it (shield 1).

Item records: 63 bytes in ITEMn.DAX / MONnITM.DAX (little-endian), 72 bytes
in a saved character's .SWG file (big-endian). Both start with the item's
name (length byte + text in DAX, C string in SWG)::

    DAX   SWG
    0x2E  0x30  type (index into the type table)
    0x2F  0x32  name words 1, 2, 3 (indexes into the item word list of the
    0x30  0x33    executable); the name reads word 3, word 2, word 1:
    0x31  0x34    3c 4d 5a 08 = Mace / of / Disruption -> "Mace of Disruption"
    0x32  0x37  magical plus (signed; charges for wands and necklaces)
    0x34  0x3A  readied
    0x35  0x3B  hidden name words until identified (bit 2 word 1, bit 1 word 2)
    0x36  0x3D  cursed
    0x37  0x3E  weight (u16)
    0x39  0x40  count (arrows, darts...)
    0x3A  0x42  value in steel pieces (u16)
    0x3C  0x44  three effect bytes: the spells on a scroll, charges...
(SWG fields are word-aligned; 0x31 and 0x35 hold leftover memory.)
"""

ARROWS, MISSILE, MELEE, THROWN, QUARRELS = 0x01, 0x02, 0x04, 0x10, 0x80
ARROW, QUARREL = 30, 12

WEAPONS = {
    1: 'Battle Axe', 2: 'Hand Axe', 3: 'Club', 4: 'Dagger', 5: 'Dart', 6: 'Hammer',
    7: 'Javelin', 8: 'Mace', 9: 'Morning Star', 10: 'Military Pick', 11: 'Awl Pike',
    12: 'Quarrel', 13: 'Scimitar', 14: 'Spear', 15: 'Quarter Staff', 16: 'Bastard Sword',
    17: 'Broad Sword', 18: 'Long Sword', 19: 'Short Sword', 20: 'Two-Handed Sword',
    21: 'Trident', 22: 'Composite Long Bow', 23: 'Composite Short Bow', 24: 'Long Bow',
    25: 'Short Bow', 26: 'Fine Bow', 27: 'Light Crossbow', 28: 'Sling', 29: 'Staff Sling',
    30: 'Arrow', 67: 'Hoopak',
}


class ItemType:
    __slots__ = ('index', 'slot', 'hands', 'large', 'half_attacks', 'armour', 'dice', 'range', 'classes',
                 'flags')

    def __init__(self, index, r):
        self.index = index
        self.slot, self.hands = r[0], r[1]
        self.large = (r[2], r[3], _s8(r[4]))
        self.half_attacks = r[5]
        self.armour = r[6]
        self.dice = (r[9], r[10], _s8(r[11]))
        self.range = r[12]
        self.classes = r[13]
        self.flags = r[14]

    @property
    def is_missile(self):
        """Fires or throws at range (bows, crossbows, slings, darts, javelins...)."""
        return self.range > 0 and bool(self.flags & (MISSILE | THROWN)) and self.slot == 0

    @property
    def launcher(self):
        """Bow / crossbow / sling: useless in melee, cannot be used next to an enemy."""
        return self.is_missile and not self.flags & (MELEE | THROWN)

    @property
    def ammo(self):
        """Item type of the ammunition it needs, or None."""
        if self.flags & QUARRELS:
            return QUARREL
        if self.flags & ARROWS:
            return ARROW
        return None

    @property
    def name(self):
        return WEAPONS.get(self.index, 'item %d' % self.index)


def _s8(b):
    return b - 256 if b > 127 else b


def load_types(data):
    """The "items" file -> {type: ItemType}."""
    body = data[2:]
    return {i: ItemType(i, body[i * 16:(i + 1) * 16]) for i in range(len(body) // 16)}


class Item:
    FIELDS = ('name', 'type', 'ready', 'quantity', 'words', 'plus', 'hidden', 'cursed', 'weight',
              'value', 'effects')
    __slots__ = FIELDS

    def __init__(self, name, type_, ready=False, quantity=1, words=(0, 0, 0), plus=0, hidden=0,
                 cursed=False, weight=0, value=0, effects=(0, 0, 0)):
        self.name, self.type, self.ready, self.quantity = name, type_, ready, quantity
        self.words, self.plus, self.hidden, self.cursed = tuple(words), plus, hidden, cursed
        self.weight, self.value, self.effects = weight, value, tuple(effects)

    def to_list(self):
        return [getattr(self, f) for f in self.FIELDS]

    @classmethod
    def from_list(cls, v):
        return cls(*v)

    def title(self, words=None, identified=None, types=None):
        """The name as the player sees it: hidden words and the plus stay
        hidden until the item is identified. The plus is shown for weapons
        and armour (given the type table)."""
        known = (self.hidden == 0) if identified is None else identified
        parts = []
        if words:
            for k in (2, 1, 0):                  # word 3 first
                w = self.words[k]
                if w and (known or not self.hidden & (4 >> k)):
                    parts.append(words.get(w, ''))
        text = ' '.join(p for p in parts if p) or self.name
        t = types.get(self.type) if types else None
        if self.plus and known and (types is None or (t is not None and t.slot in (0, 1, 2)
                                                         and self.type != BRACERS)):
            text += ' %+d' % self.plus
        if self.quantity > 1:
            text = '%d %s%s' % (self.quantity, text, '' if text.endswith('s') else 's')
        return text

    def __repr__(self):
        return '<%s t%d%s x%d>' % (self.name, self.type, ' ready' if self.ready else '', self.quantity)


def parse_swg(data):
    """A saved character's items (72-byte records)."""
    out = []
    for k in range(0, len(data) - 71, 72):
        r = data[k:k + 72]
        name = r[:42].split(b'\0')[0].decode('latin-1').strip()
        for prefix in ('Yes ', 'No '):
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        out.append(Item(name, r[0x30], bool(r[0x3A]), r[0x40] or 1, (r[0x32], r[0x33], r[0x34]),
                        _s8(r[0x37]), r[0x3B], bool(r[0x3D]), r[0x3E] << 8 | r[0x3F],
                        r[0x42] << 8 | r[0x43], (r[0x44], r[0x45], r[0x46])))
    return out


def parse_dax_item(r):
    name = r[1:1 + min(r[0], 41)].decode('latin-1').strip()
    return Item(name, r[0x2E], bool(r[0x34]), r[0x39] or 1, (r[0x2F], r[0x30], r[0x31]), _s8(r[0x32]),
                r[0x35], bool(r[0x36]), r[0x37] | r[0x38] << 8, r[0x3A] | r[0x3B] << 8,
                (r[0x3C], r[0x3D], r[0x3E]))


def parse_dax_items(data, monster=False):
    """Item records from ITEMn/MONnITM.DAX (63 bytes). Monster item names are
    junk, so those are named from the weapon list and given a supply of 20."""
    out = []
    for k in range(0, len(data) - 62, 63):
        r = data[k:k + 63]
        if monster:
            out.append(Item(WEAPONS.get(r[0x2E], 'item'), r[0x2E], True, 20))
        else:
            out.append(parse_dax_item(r))
    return out


def load_words(exe):
    """{number: word} of the item name words in the executable (1 Battle Axe ...)."""
    i = exe.find(b'Battle Axe\0')
    words = {}
    for n in range(1, 256):
        if i < 0:
            break
        j = exe.index(b'\0', i)
        words[n] = exe[i:j].decode('latin-1')
        i = j + 1
    return words


# --- equipment -----------------------------------------------------------------------
DEX_AC = {3: 4, 4: 3, 5: 2, 6: 1, 15: -1, 16: -2, 17: -3, 18: -4, 19: -4}
BRACERS = 50


def armour_value(t):
    b = t.armour & 0x7F
    return b - 0x32 if b >= 0x32 else b


def armour_class(items, types, dex, words=None):
    """AD&D AC from the readied armour, shield, bracers... and dexterity."""
    body, worn = 0, 0
    for it in items:
        t = types.get(it.type)
        if not it.ready or t is None or t.slot == 0:
            continue
        if it.type == BRACERS and words:
            # "Bracers AC 4": protection as that armour, not added to body armour
            ac = next((int(words[w][3:]) for w in it.words if w and words.get(w, '').startswith('AC ')), 10)
            body = max(body, 10 - ac)
        elif t.armour & 0x7F >= 0x32:
            body = max(body, armour_value(t) + it.plus)
        elif t.armour:
            worn += armour_value(t) + it.plus
        elif it.plus and t.slot not in (10,):
            worn += it.plus                    # rings, cloaks of protection
    return 10 - body - worn + DEX_AC.get(dex, 0)


def melee_weapon(items, types):
    """(Item, ItemType) of the readied hand weapon, or (None, None) for fists."""
    for it in items:
        t = types.get(it.type)
        if it.ready and t is not None and t.slot == 0 and not t.launcher:
            return it, t
    return None, None


def can_ready(item, items, types):
    """Why this item cannot be readied alongside the others (None if it can)."""
    t = types.get(item.type)
    if t is None:
        return 'cannot be readied'
    # bows and slings are slung on the back: they never fill the hands
    hands = sum(types[i.type].hands for i in items
                if i.ready and i is not item and i.type in types and not types[i.type].launcher)
    if t.hands and not t.launcher and hands + t.hands > 2:
        return 'your hands are full'
    for o in items:
        if o is item or not o.ready or o.type not in types:
            continue
        ot = types[o.type]
        if t.slot != 10 and ot.slot == t.slot and not (t.slot == 0 and (t.launcher or ot.launcher)):
            return 'already using ' + o.name
    return None


def best_missile(items, types):
    """(launcher Item, ItemType, ammo Item or None) the owner can shoot with, or None."""
    for it in sorted(items, key=lambda i: not i.ready):
        t = types.get(it.type)
        if t is None or not t.is_missile:
            continue
        need = t.ammo
        if need is None:
            return it, t, None
        ammo = next((a for a in items if a.type == need and a.quantity > 0), None)
        if ammo is not None:
            return it, t, ammo
    return None


DEX_MISSILE = {3: -3, 4: -2, 5: -1, 16: 1, 17: 2, 18: 3, 19: 3}


def dex_missile_bonus(dex):
    return DEX_MISSILE.get(dex, 0)
