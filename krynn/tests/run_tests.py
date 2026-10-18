#!/usr/bin/env python3
"""Checks against your copy of the game (skipped when it is not found).

    python3 tests/run_tests.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'remake'))

from cok import gfx  # noqa: E402
from cok.dax import Container  # noqa: E402
from cok.ecl import EclBlock, OPCODES  # noqa: E402
from cok.gamefiles import GameFiles  # noqa: E402
from cok.geo import GeoMap  # noqa: E402


def test_containers(gf):
    for name in gf.names():
        if '/' in name or not name.endswith(('.dax', '.daa')) or name == 'pointers.daa':
            continue
        c = Container(gf.read(name), name)
        for i in c.ids():
            e = c.entries[i]
            data = c.get(i)
            if e.raw_size is not None and not (name.startswith('8x8d') and i == 0xC9):
                assert len(data) == e.raw_size, (name, i)


def test_pictures(gf):
    n = 0
    for name in gf.names():
        if '/' in name or not name.endswith('.daa') or name.startswith(('8x8d', 'pointers')):
            continue
        c = Container(gf.read(name), name)
        for i in c.ids():
            p = gfx.decode_anim(c.get(i)) if c.kind == 'anim' else gfx.decode_block(c.get(i))
            assert p and p.frames and len(p.frames[0]) == p.width * p.height, (name, i)
            n += 1
    assert n > 250, n


def test_ecl(gf):
    for name in ('ecl1.dax', 'ecl2.dax'):
        c = Container(gf.read(name), name)
        for i in c.ids():
            e = EclBlock(c.get(i), i)
            code = e.trace()
            assert all(ins.op in OPCODES for ins in code.values()), (name, i)
            if i != 0x39:     # the demo block: its tail is only reached by the demo player
                assert sum(ins.size for ins in code.values()) > len(e.code) * 0.8, (name, i)


def test_geo(gf):
    for name in ('geo1.dax', 'geo2.dax'):
        c = Container(gf.read(name), name)
        for i in c.ids():
            g = GeoMap(c.get(i), i)
            assert max(t for row in g.squares for s in row for t in s.walls.values()) <= 15


def test_story_reaches_throtl(gf):
    """New game -> leave the outpost -> walk to Throtl -> first steps inside."""
    w = _throtl_world(gf)
    assert w.vm.block_id == 0x20 and w.in_dungeon and w.geo_id == 0x20, (w.vm.block_id, w.geo_id)
    assert (w.x, w.y) == (7, 13), (w.x, w.y)


def _throtl_world(gf):
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.vm.rng.seed(1)

    def drive(g):
        ans = None
        for _ in range(10000):
            try:
                r = g.send(ans)
            except StopIteration:
                return
            ans = None
            if r[0] == 'menu':
                items = r[1]
                if 'ATTACK' in items:
                    ans = items.index('ATTACK')     # the guards at Throtl's gate
                elif 'LEAVE' in items:
                    ans = items.index('LEAVE')
                elif 'YES' in items:
                    ans = 1 if w.vm.get_string(0x7B2C) in ('AN OUTPOST', 'WILD') else 0
                else:
                    ans = 0
            elif r[0] == 'combat':
                ans = True
    drive(w.start())
    for act in ('right', 'forward', 'forward', 'forward', 'forward'):
        drive(w.step(act))
    w.drive = drive
    return w


def _fight(battle):
    """Let the AI play both sides to the end; check the board stays legal."""
    for _ in range(5000):
        c = battle.next_turn()
        if c is None:
            break
        for _ in battle.ai_turn(c):
            cells = [p for x in battle.all if x.present and x.status != 'fled' for p in x.cells()]
            assert len(cells) == len(set(cells)), 'two combatants share a cell'
            assert all(battle.arena.passable(*p) for p in cells), 'combatant inside a wall'
    assert battle.result in ('won', 'lost', 'fled'), battle.result
    return battle.result


def test_combat_outdoors(gf):
    import random
    from kroc import encounter
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.files.area = '2'
    b = encounter.build(w, [(1, 4, 1)], random.Random(2))       # the caravan's 4 Baaz
    assert [e.name for e in b.enemies] == ['BAAZ'] * 4
    assert b.enemies[0].ac == 4 and b.enemies[0].thac0 == 16 and b.enemies[0].attacks[0].text() == '1d8'
    assert _fight(b) in ('won', 'lost')


def test_combat_dungeon(gf):
    import random
    from cok import blocks
    from kroc import encounter
    w = _throtl_world(gf)
    b = encounter.build(w, [(9, 5, 9)], random.Random(3))       # goblins in Throtl
    ids = {bid for row in b.arena.block for bid in row if bid}
    assert any(i.startswith('W1-') for i in ids), ids
    assert all(blocks.parse(i)['kind'] in ('wall', 'door', 'edge') for i in ids), ids
    big = [e for e in encounter.build(w, [(0x10, 1, 0x10)], random.Random(1)).enemies]
    assert big and (big[0].w, big[0].h) == (1, 2), 'minotaur icon is 24x48'
    _fight(b)


def test_journal(gf):
    """References in story text are found; the extracted journal (if any) is complete."""
    from kroc.journal import Journal
    refs = Journal.references("SIR KARL CONTINUES, AND YOU RECORD IT IN JOURNAL ENTRY 51.")
    assert refs == [('journal', 51)], refs
    assert Journal.references('YOU OVERHEAR TAVERN TALE NUMBER 12') == [('tavern', 12)]
    j = Journal()
    if not j.available:
        print('     (no extracted/journal/journal.json: run tools/journal.py MANUAL.pdf)')
        return
    assert all(j.entry('journal', n) for n in range(1, 89)), 'journal entries 1-88'
    assert all(j.entry('tavern', n) for n in range(1, 58)), 'tavern tales 1-57'
    assert 'Paladine' in ' '.join(j.entry('journal', 51)['text'])


def test_missiles(gf):
    """Bows and darts: line of sight, range, no shooting in melee, ammunition used up."""
    import random
    from kroc import encounter
    from kroc.combat import Arena, Battle, Combatant, Attack, Missile, PARTY, ENEMY
    from cok.items import Item
    a = Arena(12, 5, 'F-DUNG')
    arrows = Item('Arrows', 30, True, 10)
    archer = Combatant('ARCHER', PARTY, 10, 10, 5, 15, [Attack(2, 1, 6)], 12, ('party', None))
    archer.missile = Missile('Short Bow', 1, 6, 0, 2, 8, 15, arrows, 'arrows', 'ammo')
    gob = Combatant('GOBLIN', ENEMY, 50, 50, 6, 20, [Attack(2, 1, 6)], 6, ('monster', 9, '1'))
    b = Battle(a, [archer], [gob], random.Random(1))
    archer.x, archer.y, gob.x, gob.y = 1, 2, 7, 2
    assert b.fire_problem(archer, gob) is None
    a.block[2][4] = 'W1-01-01'                       # a wall in the way
    assert b.fire_problem(archer, gob) == 'no clear shot'
    a.block[2][4] = None
    gob.x = 11
    assert b.fire_problem(archer, gob).startswith('out of range')
    gob.x = 2
    assert b.fire_problem(archer, gob) == 'an enemy is next to you'
    gob.x = 6
    b.fire(archer, gob)
    assert arrows.quantity == 8 and archer.attacked
    # a real fight: the party's bows against Mysellia and two dart-throwing mages
    w = _throtl_world(gf)
    w.files.area = '1'
    b = encounter.build(w, [(0x36, 1, 0), (0x27, 2, 0)], random.Random(4))
    assert sum(1 for c in b.party if c.missile) >= 4
    _fight(b)
    assert any('shoots' in ln for ln in b.log_lines), 'nobody shot'


def test_spells(gf):
    """Sleep, Magic Missile, Fireball friendly fire, Hold + coup de grace, charm, AI casting."""
    import random
    from kroc import encounter, spells as SP
    from kroc.combat import Arena, Battle, Combatant, Attack, PARTY, ENEMY, DEAD

    def setup(seed=1):
        a = Arena(20, 12, 'F-DUNG')
        mage = Combatant('MAGE', PARTY, 10, 10, 8, 19, [Attack(2, 1, 4)], 12, ('party', None))
        mage.levels = {'C': 0, 'M': 5}
        friend = Combatant('FIGHTER', PARTY, 30, 30, 3, 15, [Attack(2, 1, 8)], 12, ('party', None))
        gobs = [Combatant('GOBLIN', ENEMY, 6, 6, 6, 20, [Attack(2, 1, 6)], 6, ('monster', 9, '1'))
                for _ in range(4)]
        ogre = Combatant('OGRE', ENEMY, 30, 30, 5, 15, [Attack(2, 1, 10)], 9, ('monster', 9, '1'))
        ogre.hd = 5
        b = Battle(a, [mage, friend], gobs + [ogre], random.Random(seed))
        mage.x, mage.y, friend.x, friend.y = 2, 5, 3, 6
        for k, g in enumerate(gobs):
            g.x, g.y = 10 + k % 2, 5 + k // 2
        ogre.x, ogre.y = 11, 7
        return b, mage, friend, gobs, ogre

    b, mage, friend, gobs, ogre = setup()
    sleep = SP.spell(21)
    mage.spells = [21, 15, 47, 47]
    hit = SP.victims(b, mage, sleep, (10, 6))
    assert set(gobs) <= set(hit) and ogre in hit
    assert SP.problem(b, mage, sleep, (19, 6)).startswith('out of range')
    SP.cast(b, mage, sleep, (10, 6))
    assert all(g.has('asleep') for g in gobs) and not ogre.has('asleep'), 'ogre has too many HD'
    assert mage.spells == [15, 47, 47] and SP.problem(b, mage, SP.spell(15), ogre) == 'already acted'
    # helpless victims are slain outright in melee
    friend.x, friend.y = 9, 5
    b.attack(friend, gobs[0])
    assert gobs[0].status == DEAD
    # magic missile never misses; level 5 = 3 missiles
    mage.attacked = False
    before = ogre.hp
    SP.cast(b, mage, SP.spell(15), ogre)
    assert 6 <= before - ogre.hp <= 15
    # fireball hits the friend standing in the blast too
    mage.attacked = False
    fb = SP.spell(47)
    assert friend in SP.victims(b, mage, fb, (10, 6))
    hp = friend.hp
    SP.cast(b, mage, fb, (10, 6))
    assert friend.hp < hp and gobs[1].status == DEAD
    # the AI does not fireball its own side
    b, mage, friend, gobs, ogre = setup(2)
    mage.spells = [47]
    friend.x, friend.y = 10, 4
    pick = SP.choose(b, mage)
    assert pick is None or friend not in SP.victims(b, mage, pick[0], pick[1])
    # hold person, then charm: the ogre changes sides and back again
    b, mage, friend, gobs, ogre = setup(3)
    ogre.save_spell = 21                     # never saves
    SP.spell(49).effect(b, mage, ogre, SP.spell(49), 5)
    assert ogre.helpless and b.to_hit(friend, ogre) == 1.0
    ogre.conditions.clear()
    b.charm(ogre, mage, 2)
    assert ogre in b.party and ogre.side == PARTY and ogre.auto
    b.tick_magic(ogre)
    b.tick_magic(ogre)
    assert ogre in b.enemies and ogre.side == ENEMY
    # a full fight with the real party's spells against Bozaks (casters)
    w = _throtl_world(gf)
    w.files.area = '1'
    for ch in w.party:
        ch.spells = list(ch.memorised)
    b = encounter.build(w, [(4, 3, 0)], random.Random(5))
    assert any(c.spells for c in b.party) and all(e.spells for e in b.enemies)
    for c in b.party:
        c.auto = True
    _fight(b)
    assert any(' casts ' in ln for ln in b.log_lines), 'nobody cast a spell'
    b.finish()
    assert sum(len(ch.spells) for ch in w.party) < sum(len(ch.memorised) for ch in w.party)
    w.rest()
    assert all(ch.spells == ch.memorised for ch in w.party if not ch.dead)


def test_morale(gf):
    """Beaten monsters run for the edge and give no experience; the mindless never run."""
    import random
    from kroc import encounter
    from kroc.combat import Arena, Battle, Combatant, Attack, PARTY, ENEMY, DEAD, FLED
    assert encounter.morale('SKELETAL KNIGHT', 5) is None and encounter.morale('GOBLIN', 1) == 46
    a = Arena(12, 7, 'F-DUNG')
    hero = Combatant('HERO', PARTY, 40, 40, 2, 10, [Attack(2, 1, 8)], 12, ('party', None))
    gobs = [Combatant('GOBLIN', ENEMY, 6, 6, 6, 20, [Attack(2, 1, 6)], 6, ('monster', 9, '1'), xp=10)
            for _ in range(4)]
    b = Battle(a, [hero], gobs, random.Random(1))
    hero.x, hero.y = 2, 3
    for k, g in enumerate(gobs):
        g.x, g.y, g.morale = 8, 1 + k, 0           # morale 0: always breaks
    gobs[0].status = gobs[1].status = DEAD
    b.start_round()
    assert gobs[2].has('fleeing') and gobs[3].has('fleeing')
    b.order = [gobs[2]]
    c = b.next_turn()
    list(b.ai_turn(c))
    assert c.status == FLED, (c, c.status)
    # a fleeing monster cornered in a closed room fights on
    a2 = Arena(5, 5, 'F-DUNG')
    for i in range(5):
        a2.block[0][i] = a2.block[4][i] = a2.block[i][0] = a2.block[i][4] = 'W1-01-01'
    hero2 = Combatant('HERO', PARTY, 40, 40, 2, 10, [Attack(2, 1, 8)], 12, ('party', None))
    rat = Combatant('RAT', ENEMY, 3, 3, 8, 20, [Attack(2, 1, 3)], 12, ('monster', 8, '1'))
    b2 = Battle(a2, [hero2], [rat], random.Random(2))
    hero2.x, hero2.y, rat.x, rat.y = 1, 1, 3, 3
    rat.conditions['fleeing'] = 999
    b2.next_turn()
    b2.turn = rat
    rat.half_moves = 24
    list(b2.ai_turn(rat))
    assert not rat.has('fleeing') and rat.status != FLED
    # whole fight: experience only for the dead
    b.order = []
    for g in gobs[3:]:
        g.status = FLED
    b.check_end()
    assert b.result == 'won' and b.finish() == 20


def test_save_load(gf):
    """A game saved in Throtl comes back identical and plays on the same way."""
    import random
    import tempfile
    from kroc import savegame
    w = _throtl_world(gf)
    w.party[1].hp -= 5
    w.party[2].spells.remove(21)
    w.journal_found.append(('journal', 3))
    data = savegame.snapshot(w, {(0x20, 7, 13)})
    w2, visited = savegame.restore(json_roundtrip(data), w.files)
    again = savegame.snapshot(w2, visited)
    for k in data:
        if k != 'saved':
            assert data[k] == again[k], k
    assert w2.slots is not None and w2.slots.ids == w.slots.ids, 'wall sets restored'
    assert w2.party[1].hp == w.party[1].hp and w2.party[2].spells == w.party[2].spells
    # both play on identically
    for world in (w, w2):
        world.vm.rng = random.Random(9)
        for act in ('forward', 'left', 'forward', 'forward'):
            w.drive(world.step(act))
    assert (w.x, w.y, w.facing, w.vm.block_id) == (w2.x, w2.y, w2.facing, w2.vm.block_id)
    assert w.vm.mem == w2.vm.mem
    # files on disk: slots, listing, atomic write
    old = savegame.DIR
    savegame.DIR = tempfile.mkdtemp()
    try:
        savegame.save('C', w2, visited)
        info = dict((s, lbl) for s, lbl, _ in savegame.listing())
        assert info['C'] and info['A'] is None, info
        w3, _ = savegame.load('C', w.files)
        assert (w3.x, w3.y) == (w2.x, w2.y)
    finally:
        savegame.DIR = old


def test_camp(gf):
    """Spell slots match the saved party; moons; rest, fix and an interrupted night."""
    from kroc import magic
    from kroc.world import REST_CHANCE, REST_INTERVAL
    w = _throtl_world(gf)
    garin = next(c for c in w.party if c.name == 'GARIN')
    kal = next(c for c in w.party if c.name == 'KAL')
    for c in w.party:
        assert magic.fit(c, c.memorised, 0)[1] == [], (c.name, 'saved spells must fit day 0')
    assert 21 in magic.known(garin)['M'] and 47 not in magic.known(garin)['M']
    assert 3 in magic.known(kal)['C'] and 4 not in magic.known(kal)['C'], 'no evil reversals'
    # Lunitari (Garin's Red Robes) in low sanction on day 14: no bonus spells
    assert magic.moon_phase(2, 14) == 'low sanction'
    assert len(magic.fit(garin, garin.memorised, 14)[0]) == 2
    # Fix: the clerics' cures first, then nights until everyone is whole
    w.party[0].hp = 3
    kal.spells.remove(21)
    start = w.minutes
    lines = []
    for r in w.camp('fix'):
        if r[0] == 'print':
            lines.append(r[1])
        assert r[0] != 'combat', 'Throtl was not given a 100% chance here'
    assert not w.party_hurt() and not w.spells_missing(), lines
    assert any('Cure Light Wounds' in ln for ln in lines) and w.minutes > start
    # a night with a sure interruption runs the block's campint: an ambush
    real = w.vm.get
    w.vm.get = lambda loc: {REST_CHANCE: 100, REST_INTERVAL: 96}.get(loc & 0xFFFF, None) or real(loc)
    kinds = []
    g = w.camp('rest')
    ans = None
    for _ in range(500):
        try:
            r = g.send(ans)
        except StopIteration:
            break
        kinds.append(r[0])
        ans = True if r[0] == 'combat' else (0 if r[0] == 'menu' else None)
    w.vm.get = real
    assert 'combat' in kinds, kinds


def test_items(gf):
    """Item records and names; AC/THAC0/damage rebuilt from items; treasure and money."""
    from kroc.world import World, Files
    from cok import items as I
    w = World(files=Files(gf.source))
    types, words = w.files.item_types(), w.files.item_words()
    assert words[8] == 'Mace' and words[90] == 'of'
    mace = w.files.item_block(68)[0]
    assert mace.title(words, False, types) == 'Mace' and mace.title(words, True, types) == 'Mace of Disruption +1'
    scroll = w.files.item_block(67)[1]
    assert set(scroll.effects) == {46, 49, 52}, 'Dispel Magic, Hold Person, Protection 10ft'
    for c in w.party:                       # the saved figures come out of the items exactly
        saved = (c.ac, c.thac0, c.weapon)
        c.refresh(types, words)
        assert (c.ac, c.thac0, c.weapon) == saved, (c.name, saved, (c.ac, c.thac0, c.weapon))
    knight = w.party[0]
    plate = next(i for i in knight.items if i.type == 36)
    plate.ready = False
    knight.refresh(types, words)
    assert knight.ac == 6, knight.ac        # shield 1, DEX 17: 10 - 1 - 3
    plate.ready = True
    sword = next(i for i in knight.items if i.type == 18)
    sword.plus = 2
    knight.refresh(types, words)
    assert knight.thac0 == 15 and knight.weapon == (1, 8, 8)
    bow = I.Item('Short Bow', 25)
    knight.items.append(bow)
    assert I.can_ready(bow, knight.items, types) is None, 'a bow is slung beside the sword'
    two = I.Item('Two-Handed Sword', 20)
    assert I.can_ready(two, knight.items, types), 'no two-handed sword with a shield'
    # money: TREASURE fills the purse; paying uses the small coins first
    found, items = w.treasure([100, 0, 0, 20, 5, 1, 0, 16])
    assert found == {'silver': 100, 'platinum': 20, 'steel': 5, 'gems': 1} and len(items) == 13
    assert w.wealth() == 2 + 10 + 5
    assert w.pay(11) and w.wealth() == 6 and not w.pay(7)


def test_training(gf):
    """Levels match the manual's tables; training raises HP, THAC0, slots; mages learn a spell."""
    import random
    from kroc import training as T, magic, savegame
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    by = {c.name: c for c in w.party}
    garin, kal, molly, knight = by['GARIN'], by['KAL'], by['MOLLY'], by['SIR STRONGSWORD']
    for c in w.party:      # the saved levels sit on the right rows; THAC0 follows the matrices
        assert T.thac0_for(c.levels) == c.base_thac0, c.name
        assert not T.ready(c), c.name
    assert T.table(garin, 'magic-user') == 'red' and T.table(kal, 'magic-user') == 'white'
    assert T.table(kal, 'cleric') == 'good' and T.table(knight, 'knight') == 'crown'
    assert T.limit(molly, 'fighter') == 5, 'kender fighters stop at 5 (STR 16)'
    assert T.share(garin, 1000) == 500, 'two classes share the award'
    garin.experience = 20000             # enough for fighter 5 (18,001) and mage 4 (18,000)
    hp, slots = garin.hp_max, magic.slots(garin)
    lines = T.train(garin, random.Random(1))
    assert garin.levels['fighter'] == 4 and garin.levels['magic-user'] == 3, 'one level at a time'
    assert garin.hp_max > hp and garin.base_thac0 == 18 and garin.spell_picks == 1, lines
    assert magic.slots(garin)[(magic.MAGE, 2)] == 1 and (magic.MAGE, 2) not in slots
    assert set(T.learnable(garin)) <= T.RED and 21 not in T.learnable(garin), 'Sleep is White only'
    assert T.ready(garin) == ['fighter', 'magic-user'], 'nothing lost: training again goes on'
    T.train(garin, random.Random(1))
    assert garin.levels == dict(garin.levels, fighter=5, **{'magic-user': 4})
    # the new levels survive a save
    w2, _ = savegame.restore(json_roundtrip(savegame.snapshot(w)), w.files)
    g2 = next(c for c in w2.party if c.name == 'GARIN')
    assert g2.levels == garin.levels and g2.hp_max == garin.hp_max and g2.spell_picks == 2


def test_magic_items(gf):
    """Wands spend charges, potions are drunk, scrolls only for their robe, slaying weapons."""
    import random
    from cok.items import Item
    from kroc import encounter, magic_items as MI, spells as SP
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.files.area = '1'
    words, types = w.files.item_words(), w.files.item_types()
    pool = {it.title(words, True, types): it for it in w.files.all_items()}
    copy = lambda name: Item.from_list(pool[name].to_list())
    by = {c.name: c for c in w.party}
    knight, garin, kal = by['SIR STRONGSWORD'], by['GARIN'], by['KAL']
    knight.items += [copy('Wand of Fireballs'), copy('Potion of Healing')]
    garin.items.append(copy('Red MU Scroll 3 Spells'))
    kal.items.append(copy('Red MU Scroll 3 Spells'))
    scroll = pool['Red MU Scroll 3 Spells'].effects
    assert [p.spell.id for p in MI.powers(garin, words, types)] == [s for s in scroll if SP.SPELLS[s].combat]
    assert not MI.powers(kal, words, types), 'a White Robe cannot read a Red scroll'
    b = encounter.build(w, [(9, 6, 9)], random.Random(2))
    kc = next(c for c in b.party if c.ref is knight)
    wand = next(p for p in kc.item_powers() if 'Fireball' in p.name)
    charges = wand.item.effects[0]
    goblin = b.enemies[0]
    b.turn, kc.attacked = kc, False
    SP.cast(b, kc, wand, (goblin.x, goblin.y))
    assert wand.item.effects[0] == charges - 1 and goblin.status != 'ok'
    # the AI drinks a healing potion when badly hurt
    kc.attacked, kc.hp = False, 3
    pick = SP.choose(b, kc)
    assert pick and 'Healing' in pick[0].name, pick
    SP.cast(b, kc, *pick)
    assert kc.hp > 3 and not any('Potion' in i.name for i in knight.items)
    # the Dragonlance doubles its damage against dragons
    from kroc.combat import Battle
    kc.slayer = MI.slayer(knight, words, types)
    assert Battle.slaying(kc, goblin) == (0, 0, 1)
    knight.items.append(copy('Footmans Dragonlance +5'))
    knight.items[-1].ready = True
    assert MI.slayer(knight, words, types)[3] == 2


def test_camp_magic(gf):
    """Cures, Raise Dead (no elves), Remove Curse, Read Magic outside combat."""
    import random
    from cok.items import Item
    from kroc import camp_magic as CM
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.vm.rng = random.Random(4)
    by = {c.name: c for c in w.party}
    kal, knight, garin = by['KAL'], by['SIR STRONGSWORD'], by['GARIN']
    knight.hp = 5
    assert 3 in CM.camp_spells(kal)
    line = CM.cast(w, kal, 3, knight)
    assert knight.hp > 5 and 'Cure Light Wounds' in line and kal.spells.count(3) == 1
    kal.spells.append(67)
    knight.dead, knight.stats['CON'] = True, 18          # 100% survival
    CM.cast(w, kal, 67, knight)
    assert not knight.dead and knight.hp == 1 and knight.stats['CON'] == 17
    kal.spells.append(67)
    garin.dead = True                                    # a half-elf can be raised
    by['SIRRION'].dead = True                            # a Qualinesti elf cannot
    assert 'elves' in CM.cast(w, kal, 67, by['SIRRION']) and by['SIRRION'].dead and 67 in kal.spells
    sword = next(i for i in knight.items if i.type == 18)
    sword.cursed = True
    kal.spells.append(43)
    CM.cast(w, kal, 43, knight)
    assert not sword.cursed
    garin.dead = False
    scroll = Item('Scroll', 39, words=(0x66, 0x28, 0x78), hidden=0x24, effects=(30, 32, 45))
    garin.items.append(scroll)
    garin.spells.append(18)
    assert '3 Spells' in CM.cast(w, garin, 18) and scroll.hidden == 0


def test_gods_and_orders(gf):
    """The gods' special spells and powers; knights petitioning the next order."""
    from kroc import magic, training as T, encounter
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    by = {c.name: c for c in w.party}
    kal, sirrion, knight = by['KAL'], by['SIRRION'], by['SIR STRONGSWORD']
    assert magic.GODS[magic.deity(kal)] == 'Mishakal' and magic.GODS[magic.deity(sirrion)] == 'Majere'
    assert magic.slots(kal)[(magic.CLERIC, 'special')] == 1
    assert {91, 92, 93} <= set(magic.known(kal)[magic.CLERIC]) and 89 not in magic.known(kal)['C']
    kept, dropped = magic.fit(kal, kal.memorised + [92, 93])
    assert 92 in kept and 93 in dropped, 'one special slot at cleric level 2'
    assert magic.heal_bonus_dice(kal) == 1 and magic.heal_bonus_dice(sirrion) == 0
    assert magic.god_hit_bonus(kal) == 0
    # petitioning: experience and ability scores
    joined, line = T.petition(knight)
    assert not joined and '12000' in line, line
    knight.experience = 13000
    joined, line = T.petition(knight)
    assert joined and knight.raw[0x5D] == 2 and knight.levels['knight'] == 3, line
    assert T.table(knight, 'knight') == 'sword'
    knight.stats['CON'] = 12
    knight.experience = 30000
    assert not T.petition(knight)[0], 'the Rose wants CON 15'
    # seventh-level fighters strike three times in two rounds
    knight.levels['knight'] = 7
    c = encounter.party_combatant(knight, w.files.item_types())
    assert c.attacks[0].half == 3


def test_vault(gf):
    """The outpost vault script banks and pays out the party's steel."""
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.purse['steel'] = 1000
    plan = ['NEXT', 'VAULT', 'DEPOSIT', 500, 'WITHDRAW', 300, 'EXIT']
    g, ans, done = w.start(), None, False
    for _ in range(20000):
        try:
            r = g.send(ans)
        except StopIteration:
            break
        ans = None
        if r[0] == 'number':
            ans = plan.pop(0)
        elif r[0] == 'treasure':
            w.treasure(r[1])
        elif r[0] == 'combat':
            ans = True
        elif r[0] == 'menu':
            items = r[1]
            if plan and plan[0] in items:
                ans = items.index(plan.pop(0))
                if not plan:
                    done = True
                    break
            else:
                ans = 0
    assert done, plan
    assert w.vm.get(0x4C33) == 2, 'five hundred in, three out'
    assert w.purse['steel'] == 1000 - 520 + 280


def test_creation(gf):
    """Every race and class combination builds a sound character that saves and trains."""
    import random
    from kroc import creation as C, training as T, magic, savegame
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    types, words = w.files.item_types(), w.files.item_words()
    rng = random.Random(11)
    assert C.combos_for(6) == [(c,) for c in ('cleric', 'fighter', 'ranger', 'magic-user', 'thief', 'knight')]
    assert ('magic-user',) not in C.combos_for(5), 'no kender mages'
    assert C.gods_for(4, race=4) == [6], 'dwarven clerics serve Reorx'
    made = []
    for race in range(7):
        for combo in C.combos_for(race):
            align = C.alignments_for(combo, race)[0]
            for _ in range(500):
                stats = C.roll_stats(rng, race, combo)
                if not C.qualifies(stats, combo):
                    break
            ch = C.build('T%d%d' % (race, len(made)), race, combo, align, stats, rng, types, words)
            assert ch.hp_max > 0 and all(ch.levels[c] >= 1 for c in combo), (race, combo)
            assert ch.thac0 <= 24 and -2 <= ch.ac <= 10, (race, combo, ch.thac0, ch.ac)
            assert magic.fit(ch, ch.memorised)[1] == [], (race, combo)
            assert 'knight' not in combo or ch.levels['knight'] == 1
            made.append(ch)
    w.party = made[:6]
    w2, _ = savegame.restore(json_roundtrip(savegame.snapshot(w)), w.files)
    for a, b in zip(w.party, w2.party):
        assert (a.levels, a.hp_max, a.ac, a.thac0, a.weapon, a.book, a.alignment) == \
            (b.levels, b.hp_max, b.ac, b.thac0, b.weapon, b.book, b.alignment), a.name
    hero = made[0]
    hero.experience += 100000
    assert T.train(hero, rng), 'a new character trains like any other'


def test_sound(gf):
    """The instrument bank, every named sound, the pitch of a note, the title music."""
    from cok import sound as S
    bank = S.read_bank(gf.read('sound/sounddata'))
    assert {'square', 'saw', 'tri', 'odd', 'odd2'} <= {k for k, v in bank.items() if isinstance(v, S.Sample)}
    assert bank['in2'] == {'PTCH': 'slowtrem', 'VLUM': 'basicEnv', 'SAMP': 'tri'}
    synth = S.Synth(bank, lambda n: gf.read('sound/' + n) if 'sound/' + n in gf else None)
    for name in ('hit', 'swish', 'arrow', 'fireb', 'light', 'cast', 'spell', 'dead0', 'gate', 'turn'):
        wave = synth.render(synth.find(name))
        assert len(wave) > S.RATE // 50 and max(abs(v) for v in wave) > 0.1, name
    a4 = synth.render(synth.find('in1'), 0.5, 69)[2000:2000 + S.RATE // 4]
    assert abs(sum(1 for x, y in zip(a4, a4[1:]) if x <= 0 < y) * 4 - 440) <= 4, 'A4 is 440 Hz'
    tempo, insts, tracks = S.read_smus(gf.read('sound/krynn'))
    assert tempo == 120 and len(tracks) == 4 and insts[0] == 'in1'
    pcm = S.render_music(gf.read('sound/krynn'), synth)
    assert 80 < len(pcm) / 2 / S.RATE < 95, len(pcm) / 2 / S.RATE


def test_script_instructions(gf):
    """DAMAGE, ROB, FIND/DESTROY ITEMS, SPELL, CHECKPARTY, ADD NPC and the window."""
    import random
    from cok.ecl import OPCODES
    from kroc.world import World, Files
    from kroc import encounter
    assert OPCODES[0x36] == ('ADD NPC', 2), 'ADD NPC takes the companion and its morale'
    w = World(files=Files(gf.source))
    w.files.area = '1'
    w.vm.rng = random.Random(1)
    knight = w.party[0]
    # the character window
    w.select_character(0)
    assert w.vm.get(0x7CCD) == 1 and w.vm.get(0x7D19) == knight.hp and w.vm.get(0x7C61) == 1
    w.vm.set(0x7D19, 3)
    assert knight.hp == 3
    w.select_character(3)                                 # Molly: a thief
    assert w.vm.get(0x7CCC) == 2 and w.vm.get(0x7CA6) > 0 and w.vm.get(0x7D00) == 1
    # DAMAGE: everyone (save for half), one character, a volley of arrows
    hp = [c.hp for c in w.party]
    w.damage_party(0xC0, 1, 10, 0, 0)
    assert all(c.hp < h for c, h in zip(w.party, hp))
    w.select_character(1)
    w.damage_party(0x80, 1, 1, 254, 128)
    assert w.party[1].dead
    lines = w.damage_party(4, 1, 6, 0, 44)
    assert len(lines) >= 4
    # ROB: a knight's tithe costs the shared purse nothing; a thief takes a share
    w.purse['steel'] = 600
    w.select_character(0)
    w.rob(0, 100)
    assert w.purse['steel'] == 600
    w.rob(1, 50)
    assert w.purse['steel'] == 300
    # items and spells
    assert w.find_item(18) and not w.find_item(63)
    w.destroy_items(18)
    assert not w.find_item(18)
    assert w.who_has_spell(21) == 2 and w.who_has_spell(47) == 255
    lo, hi, best, count = w.check_party(0x11B, 12)
    assert lo <= hi and count >= 0
    # ADD NPC: Strangbourn the knight joins, fights on his own, at most two companions
    line = w.add_npc(34, 100)
    sb = w.party[-1]
    assert 'STRANGBOURN' in line and sb.npc and sb.levels['knight'] == 4 and sb.raw[0x5D] == 1
    c = encounter.party_combatant(sb, w.files.item_types())
    assert c.auto and c.morale == 100
    w.add_npc(54, 80)
    assert 'no room' in w.add_npc(44, 100)


def test_specials(gf):
    """Dragon breath, draconian deaths, undead immunity and turning, venom, ailments."""
    import random
    from kroc import encounter, specials as SX, spells as SP, camp_magic as CM
    from kroc.combat import Arena, Battle, Combatant, Attack, PARTY, DEAD
    from kroc.world import World, Files
    w = World(files=Files(gf.source))
    w.files.area = '1'
    red = encounter.monster_combatant(w, 21, 0)
    assert SX.BREATH in red.specials and 200 + sorted(SX.BREATHS).index(0x68) in red.spells
    bozak = encounter.monster_combatant(w, 4, 0)
    ghoul = encounter.monster_combatant(w, 7, 0)
    assert SX.BONES in bozak.specials and ghoul.undead and SX.GHOUL in ghoul.specials
    a = Arena(16, 9, 'F-DUNG')
    hero = Combatant('HERO', PARTY, 30, 30, 5, 15, [Attack(2, 1, 8)], 12, ('party', None))
    b = Battle(a, [hero], [bozak, ghoul], random.Random(3))
    hero.x, hero.y, bozak.x, bozak.y, ghoul.x, ghoul.y = 4, 4, 5, 4, 9, 4
    hp = hero.hp
    b.damage(bozak, 999, 'the bozak falls.')
    assert bozak.status == DEAD and any('bones explode' in ln for ln in b.log_lines)
    assert hero.hp <= hp
    # sleep and hold do not touch the undead
    SP.spell(21).effect(b, hero, ghoul, SP.spell(21), 5)
    assert not ghoul.has('asleep')
    # a priest of Majere turns them
    w.party[4].raw = w.party[4].raw[:0x5E] + bytes([2]) + w.party[4].raw[0x5F:]
    cleric = encounter.party_combatant(w.party[4], w.files.item_types())
    assert SX.turn_level(cleric) == 4                    # cleric 2, Majere +2
    b2 = Battle(a, [cleric], [ghoul], random.Random(5))
    cleric.x, cleric.y = 6, 4
    for _ in range(20):
        cleric.attacked = False
        SX.turn_undead(b2, cleric)
        if ghoul.has('fleeing') or ghoul.status == DEAD:
            break
    assert ghoul.has('fleeing') or ghoul.status == DEAD
    # dragon breath: as much as the dragon's hit points, and the AI uses it
    b3 = Battle(Arena(20, 12, 'F-DUNG'), [hero], [red], random.Random(1))
    hero.x, hero.y, red.x, red.y = 4, 5, 9, 5
    hero.hp = hero.hp_max = 200
    pick = SP.choose(b3, red)
    assert pick and pick[0].id >= 200, pick
    SP.cast(b3, red, *pick)
    assert hero.hp < 200
    # ailments outlast the fight; the camp cures them
    kal = w.party[4]
    pc = encounter.party_combatant(kal, w.files.item_types())
    SX.ail(pc, 'poisoned')
    assert 'poisoned' in kal.ailments
    assert any(e[0] == 'poisoned' for e in encounter.party_combatant(kal, w.files.item_types()).effects)
    kal.hp = 5
    w.night()
    assert kal.hp == 5, 'no natural healing while poisoned'
    kal.spells.append(59)
    CM.cast(w, kal, 59, kal)
    assert not kal.ailments


def json_roundtrip(d):
    import json
    return json.loads(json.dumps(d))


def main():
    try:
        gf = GameFiles(sys.argv[1] if len(sys.argv) > 1 else None)
    except FileNotFoundError as e:
        print('SKIP:', e)
        return 0
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            try:
                fn(gf)
                print('ok  ', name)
            except Exception as e:     # report and continue
                failed += 1
                print('FAIL', name, repr(e))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
