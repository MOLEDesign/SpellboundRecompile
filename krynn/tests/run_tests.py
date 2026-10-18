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
                if 'LEAVE' in items:
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
