"""Saved games: the whole state of a World as JSON.

A game can be saved whenever no script is waiting on the player (not in the
middle of a conversation, menu or fight). What is kept:

    the ECL block being run, with its code (scripts patch themselves)
    VM memory and string variables (all the module's flags)
    position, facing, the GEO map and the wall sets loaded into the slots
    the party (each character's record, hit points, experience, items, spells)
    journal entries found, the clock, the automap

Ten slots, A to J, as in the original. Files go to krynn/saves/ (or the
directory in $KRYNN_SAVES) and are kept out of git: they hold your
characters' records from the save disk.
"""
import json
import os
import time

from .world import Character, World

VERSION = 1
SLOTS = 'ABCDEFGHIJ'
DIR = os.environ.get('KRYNN_SAVES') or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'saves')
PLACE = 0x7B2C          # string variable: name of the current place


def path(slot):
    return os.path.join(DIR, 'game%s.json' % slot.upper())


def snapshot(world, visited=(), label=''):
    vm = world.vm
    return {
        'version': VERSION,
        'saved': time.strftime('%Y-%m-%d %H:%M'),
        'label': label or describe(world),
        'block': vm.block_id,
        'code': vm.block.code.hex() if vm.block else '',
        'mem': sorted([k, v] for k, v in vm.mem.items()),
        'strings': sorted([k, v] for k, v in vm.strings.items()),
        'pos': [world.x, world.y, world.facing],
        'geo': world.geo_id,
        'walls': [list(w) for w in world.wall_loads],
        'party': [c.to_dict() for c in world.party],
        'selected': world.selected,
        'clock': world.clock,
        'minutes': world.minutes,
        'purse': world.purse,
        'speed': getattr(world, 'speed', 1.0),
        'journal': [list(r) for r in world.journal_found],
        'visited': sorted(list(v) for v in visited),
    }


def describe(world):
    place = world.vm.get_string(PLACE).strip().title()
    lead = world.party[0].name.title() if world.party else ''
    return ', '.join(x for x in (place, lead and lead + "'s party") if x)


def restore(data, files=None, log=None):
    """A World in the saved state, and the automap squares visited."""
    if data.get('version') != VERSION:
        raise ValueError('saved by a different version of the remake')
    w = World(files=files, log=log)
    vm = w.vm
    vm.mem = {k: v for k, v in data['mem']}
    vm.strings = {k: v for k, v in data['strings']}
    w.party = [Character.from_dict(d) for d in data['party']]
    w.selected = data['selected']
    w.clock = data['clock']
    w.minutes = data.get('minutes', w.minutes)
    w.purse.update(data.get('purse', {}))
    w.speed = data.get('speed', 1.0)
    w.journal_found = [tuple(r) for r in data['journal']]
    if data['block'] is not None:
        vm.load(data['block'])
        vm.block.code = bytes.fromhex(data['code'])
    if data['geo'] is not None:
        w.load_map(data['geo'])
    for a, b, c in data['walls']:
        w.load_walls(a, b, c)
    w.x, w.y, w.facing = data['pos']
    w.moved = False
    return w, {tuple(v) for v in data['visited']}


def save(slot, world, visited=()):
    os.makedirs(DIR, exist_ok=True)
    data = snapshot(world, visited)
    tmp = path(slot) + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, path(slot))        # never leave a half-written save behind
    return data


def load(slot, files=None, log=None):
    with open(path(slot)) as f:
        return restore(json.load(f), files, log)


def listing():
    """[(slot, label or None, saved time)] for every slot."""
    out = []
    for s in SLOTS:
        try:
            with open(path(s)) as f:
                d = json.load(f)
            out.append((s, d.get('label') or '?', d.get('saved', '')))
        except (OSError, ValueError):
            out.append((s, None, ''))
    return out
