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

Item records: 63 bytes in ITEMn.DAX / MONnITM.DAX, 72 bytes in a saved
character's .SWG file. Both start with the item's name (length byte + text
in DAX, C string in SWG); the type byte is at 0x2E (DAX) / 0x30 (SWG). In
SWG records 0x3A is 1 when the item is readied and 0x40 is the quantity
(arrows, darts...).
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
    __slots__ = ('index', 'slot', 'hands', 'large', 'half_attacks', 'dice', 'range', 'classes', 'flags')

    def __init__(self, index, r):
        self.index = index
        self.slot, self.hands = r[0], r[1]
        self.large = (r[2], r[3], _s8(r[4]))
        self.half_attacks = r[5]
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
    __slots__ = ('name', 'type', 'ready', 'quantity')

    def __init__(self, name, type_, ready=False, quantity=1):
        self.name, self.type, self.ready, self.quantity = name, type_, ready, quantity

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
        out.append(Item(name, r[0x30], bool(r[0x3A]), r[0x40] or 1))
    return out


def parse_dax_items(data):
    """Item records from ITEMn/MONnITM.DAX (63 bytes; monster item names are junk)."""
    out = []
    for k in range(0, len(data) - 62, 63):
        r = data[k:k + 63]
        out.append(Item(WEAPONS.get(r[0x2E], 'item'), r[0x2E], True, 20))
    return out


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
