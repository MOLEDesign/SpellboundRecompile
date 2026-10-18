"""Magic items in combat: potions, wands, the necklace of missiles, scrolls,
and the weapons that are deadlier against one kind of foe.

An item's powers come from its true name (the effect bytes count charges;
their effect codes are not the spell numbers). Each power behaves like a
spell, so the combat screen aims it the same way and shows what it will
hit. Wands and the necklace use up a charge, a potion is drunk, a scroll
loses the spell that was read; unidentified items work all the same.
"""
from .spells import SPELLS, Spell, condition, heal

POTIONS = {
    'Extra Healing': Spell(0, 'Potion of Extra Healing', 'C', 0, 'self', effect=heal(3, 8, 3)),
    'Healing': Spell(0, 'Potion of Healing', 'C', 0, 'self', effect=heal(2, 4, 2)),
    'Speed': Spell(0, 'Potion of Speed', 'M', 0, 'self', effect=condition('hasted', 6, save=False)),
    'Invisibility': Spell(0, 'Potion of Invisibility', 'M', 0, 'self',
                          effect=condition('invisible', 30, save=False)),
}
# charged items: name -> (spell, casting level)
CHARGED = {
    'Wand of Magic Missiles': (15, 3), 'Wand of Fireballs': (47, 6), 'Wand of Lightning': (51, 6),
    'Wand of Ice Storm': (79, 6), 'Wand of Paralyzation': (49, 6), 'Necklace of Missiles': (47, 5),
}
HEALING = {'Potion of Extra Healing', 'Potion of Healing'}


class Power:
    """A spell an item casts. Reads like a Spell (shape, range, effect...)."""

    def __init__(self, spell, label, item, owner, level=None, slot=None, charges=1):
        self.spell, self.name, self.item, self.owner = spell, label, item, owner
        self.cast_level, self.slot, self.charges = level, slot, charges

    def __getattr__(self, key):
        return getattr(self.spell, key)

    @property
    def heals(self):
        return self.spell.name in HEALING

    def use(self):
        """Spend what casting it costs; returns a line for the log or None."""
        it, ch = self.item, self.owner
        if self.slot is not None:                         # a scroll's spell is gone
            eff = list(it.effects)
            eff[self.slot] = 0
            it.effects = tuple(eff)
            if not any(SPELLS.get(s) for s in it.effects):
                ch.items.remove(it)
                return 'The scroll crumbles to dust.'
            return None
        if self.spell.name.startswith('Potion'):
            if it.quantity > 1:
                it.quantity -= 1
            else:
                ch.items.remove(it)
            return None
        eff = list(it.effects)
        eff[0] = max(0, eff[0] - 1)
        it.effects = tuple(eff)
        if eff[0] == 0:
            ch.items.remove(it)
            return 'The %s is spent.' % self.name
        return None


def powers(ch, words, types):
    """The combat powers of a character's items."""
    out = []
    red = len(ch.raw) > 0x5F and ch.raw[0x5F] in (2, 3)
    for it in ch.items:
        true = it.title(words, True, types)
        label = it.title(words, None, types)
        if 'Potion' in true:
            for key, sp in POTIONS.items():
                if key in true:
                    out.append(Power(sp, label, it, ch))
                    break
            continue
        for name, (sid, level) in CHARGED.items():
            if name in true and it.effects[0] > 0:
                out.append(Power(SPELLS[sid], '%s (%s)' % (label, SPELLS[sid].name), it, ch, level,
                                 charges=it.effects[0]))
                break
        if 'Scroll' not in true:
            continue
        mage, cleric = 'MU' in true, 'Cler' in true
        if mage and (not ch.levels.get('magic-user') or ('Red' in true) != red):
            continue                     # a mage reads only the scrolls of the order
        if cleric and not (ch.levels.get('cleric') or ch.levels.get('druid')):
            continue
        for k, sid in enumerate(it.effects):
            sp = SPELLS.get(sid)
            if sp is not None and sp.combat:
                out.append(Power(sp, '%s (scroll)' % sp.name, it, ch, slot=k))
    return out


# --- weapons that bite harder against one kind of foe ---------------------------------
DRACONIANS = ('BAAZ', 'KAPAK', 'BOZAK', 'SIVAK', 'AURAK')
REPTILES = DRACONIANS + ('DRAGON', 'SNAKE', 'LIZARD', 'CROCODILE')
UNDEAD = ('SKELET', 'ZOMBIE', 'GHOUL', 'GHAST', 'WIGHT', 'WRAITH', 'SPECTR', 'GHOST', 'MUMMY',
          'VAMPIRE', 'LICH', 'DEATH KNIGHT', 'SHADOW', 'UNDEAD')


def slayer(ch, words, types):
    """(foe words, extra to hit, extra damage, damage multiplier) of the readied weapon."""
    for it in ch.items:
        if not it.ready:
            continue
        true = it.title(words, True, types)
        if 'Dragonlance' in true:
            return (('DRAGON',), 0, 0, 2)               # the lance of legend: double damage
        if 'vs Reptiles' in true:
            return (REPTILES, 3, 3, 1)                  # +4 instead of +1
        if 'Disruption' in true:
            return (UNDEAD, 0, 0, 2)
    return None


def strength_items(ch, words, types):
    """(least hit bonus, least damage bonus) from girdles and gauntlets worn."""
    hit = dmg = None
    for it in ch.items:
        if not it.ready:
            continue
        true = it.title(words, True, types)
        if 'Ogre Power' in true:
            hit, dmg = max(hit or 0, 3), max(dmg or 0, 6)          # strength 18/00
        elif 'Giant Strength' in true:
            hit, dmg = max(hit or 0, 3), max(dmg or 0, 7)          # hill giant strength
    return hit, dmg
