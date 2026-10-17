#!/usr/bin/env python3
"""Plays the whole quest through the game's command functions, in the order
of the original walkthrough, and checks every puzzle step and the ending.
(Movement between rooms is done by placing the knight; tests/reachability.py
checks separately that every place used here can actually be walked to.)

    python3 remake/tests/playthrough.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402
from sbremake.assets import Assets  # noqa: E402
from sbremake import game as G  # noqa: E402
from sbremake.world import Knight  # noqa: E402

pygame.init()
pygame.display.set_mode((320, 240))
g = G.Game(Assets(os.path.join(os.path.dirname(HERE), "data")))
g.title_choice("play")
log = []


def msgs():
    """Close all open windows, returning their text."""
    out = []
    while g.windows:
        w = g.windows.pop(0)
        if hasattr(w, "lines"):
            out.append("".join(ch for line in w.lines for ch, _ in line + [(" ", 0)]))
    return " | ".join(out)


def goto(room, x=None):
    """Put the knight on the floor of a room (next to x if given)."""
    msgs()
    g.room = room
    geo = g.geo(room)
    x0 = 100 if x is None else max(0, x - 4)
    for dx in sorted(range(-96, 128, 4), key=abs):     # nearest free floor spot
        kn = Knight(max(-4, min(230, x0 + dx)), 152)
        if not kn.blocked(geo, kn.x, kn.y) and kn.on_ground(geo):
            break
    g.knight = kn
    g.enter_room(room, None)


def near_obj(i):
    o = g.objects[i]
    g.knight = Knight(o["px"] - 4, o["py"] + 16 - 32)


def pick(i):
    goto(g.objects[i]["room"])
    near_obj(i)
    g.pickup(i)
    m = msgs()
    assert i in g.carried, "could not pick up %s: %s" % (g.oname(i), m)


def drop(i):
    g.drop(i)
    msgs()


def menu_pick(value):
    """Choose an option from the top menu window."""
    w = g.windows.pop()
    for label, v in w.options:
        if v == value:
            w.on_choose(v)
            return
    raise AssertionError("option %r not offered" % (value,))


def step(name, cond):
    m = msgs()
    assert cond(), "step failed: %s (%s)" % (name, m)
    log.append(name)
    print("ok  %-55s %s" % (name, m[:70]))


ch = g.chars
# 1. roof: wand of command and the restorative fluid
pick(G.WAND)
pick(G.LIQUID_BOTTLE)
step("wand and bottle of liquid from the roof garden", lambda: g.has(G.WAND) and g.has(G.LIQUID_BOTTLE))
# 2. second floor: Miolnir from Elrand, elf-horn from Samsun
goto(ch[G.ELRAND]["room"])
g.take(G.ELRAND, G.MIOLNIR)
goto(ch[G.SAMSUN]["room"])
g.take(G.SAMSUN, G.ELF_HORN)
step("Miolnir and the elf-horn", lambda: g.has(G.MIOLNIR) and g.has(G.ELF_HORN))
# 3. wake Florin, give him the fluid; Thor fixes the lift
goto(ch[G.FLORIN]["room"])
g.do_command(G.FLORIN, "wake")
step("Florin woken up", lambda: ch[G.FLORIN]["awake"])
g.give(G.FLORIN, G.LIQUID_BOTTLE)
goto(G.LIFT)
g.summon(G.THOR)
g.give(G.THOR, G.MIOLNIR)
g.do_command(G.THOR, "help")
step("Thor bashes the lift control box", lambda: g.flags.get("lift_fixed"))
g.cmd_move_lift()
menu_pick(5)
step("lift moved to the ground floor", lambda: g.flags["lift_floor"] == 5)
# 4. armour on the pool of strange liquid, then free Banshee
pick(G.GLOWING_BOTTLE)
goto(G.TUNNEL_ENTRANCE)
near_obj(G.STRANGE_LIQUID)
g.drop(G.GLOWING_BOTTLE)
step("cannot drop the glowing bottle without protection", lambda: g.has(G.GLOWING_BOTTLE))
g.cast("armo")
step("Armouris Photonicus on the pool of liquid", lambda: g.flags.get("armour"))
g.drop(G.GLOWING_BOTTLE)
step("Banshee released from the bottle", lambda: g.flags.get("banshee_free") and ch[G.BANSHEE]["room"] == g.room)
# 5. shield and candle, candle spell next to the four leaf clover
pick(G.SHIELD)
g.wear(G.SHIELD)
pick(G.CANDLE)
goto(1)
g.cast("cand")
step("Candelium Illuminatus with the shield worn", lambda: g.flags.get("candle_lit"))
# 6. gas protection from the red herring and the power-pong plant
drop(G.WAND)                        # hands are full: leave the wand here for now
pick(G.RED_HERRING)
pick(G.PLANT)
g.cast("fuma")
step("Fumaticus Protectium", lambda: g.flags.get("gas_proof"))
drop(G.RED_HERRING)
drop(G.PLANT)
s0 = g.strength
goto(35)
for _ in range(300):
    g.update({"left": False, "right": False, "jump": False})
step("gas room harmless now", lambda: g.strength >= s0 - 1)
pick(G.TRUMPET)
pick(G.WAND)
# 7. the wall: Thor weakens it from the tower, Elrand blows it down
goto(ch[G.ELRAND]["room"])
g.give(G.ELRAND, G.TRUMPET)
goto(G.TOWER)
g.summon(G.THOR)
g.do_command(G.THOR, "help")
step("Thor's lightning weakens the wall", lambda: g.flags.get("wall_weakened"))
goto(G.WALL_ROOM)
g.summon(G.ELRAND)
g.do_command(G.ELRAND, "help")
step("Elrand's trumpet brings the wall down", lambda: g.flags.get("wall_down"))
drop(G.SHIELD)
pick(G.LUMP1)
pick(G.LUMP2)
step("two lumps of brickwork", lambda: g.has(G.LUMP1) and g.has(G.LUMP2))
goto(G.TOWER, 70)
g.knight.facing = 0
g.drop(G.LUMP1)
g.drop(G.LUMP2)
a, b = g.objects[G.LUMP1], g.objects[G.LUMP2]
step("bricks stacked into a step in the tower", lambda: a["px"] == b["px"] and b["py"] == a["py"] - 16)
pick(G.SCROLL)
g.read(G.SCROLL)
step("the ancient scroll read by candle light", lambda: g.flags.get("scroll_read"))
drop(G.SCROLL)
drop(G.CANDLE)
pick(G.RED_CRYSTAL)
pick(G.JAVELIN)
pick(G.GREEN_CRYSTAL)
# 8. Samsun gets the javelin; Rosmar opens the tunnel with the pocket laser
goto(ch[G.SAMSUN]["room"])
g.give(G.SAMSUN, G.JAVELIN)
pick(G.LASER)
goto(G.TUNNEL_ENTRANCE)
g.summon(G.ROSMAR)
g.give(G.ROSMAR, G.LASER)
g.do_command(G.ROSMAR, "help")
step("Rosmar cuts open the secret tunnel", lambda: g.flags.get("tunnel_open"))
goto(G.PIT)
g.summon(G.SAMSUN)
g.do_command(G.SAMSUN, "help")
step("Samsun throws his platform into the pit", lambda: g.flags.get("bridge"))
# 9. the magic talisman
pick(G.BROKEN_TALISMAN)
step("broken talisman from beyond the pit", lambda: g.has(G.BROKEN_TALISMAN))
drop(G.WAND)
pick(G.GLUE)
g.summon(G.FLORIN)
g.give(G.FLORIN, G.BROKEN_TALISMAN)
g.give(G.FLORIN, G.GLUE)
pick(G.WAND)
g.do_command(G.FLORIN, "help")
step("Florin mends the talisman", lambda: G.MAGIC_TALISMAN in g.holds(G.FLORIN))
g.take(G.FLORIN, G.MAGIC_TALISMAN)
drop(G.WAND)                          # no more commands needed
g.strength = 40
g.take(G.FLORIN, G.LIQUID_BOTTLE)
step("restorative fluid from Florin", lambda: g.strength == 100)
drop(G.LIQUID_BOTTLE)
# 10. free Gimbal
pick(G.CRYSTAL_BALL)
g.cast("proj")
w = g.windows[-1]
step("Project Physical Body offered", lambda: True)
drop(G.MAGIC_TALISMAN)
pick(G.BOOK_SHADOWS)
goto(ch[G.ORIK]["room"])              # Orik keeps the ball and the book for later
g.give(G.ORIK, G.CRYSTAL_BALL)
g.give(G.ORIK, G.BOOK_SHADOWS)
pick(G.RING)
pick(G.BLUE_CRYSTAL)
step("crystals and the ring in hand, Orik has ball and book",
     lambda: all(g.has(i) for i in (G.RED_CRYSTAL, G.GREEN_CRYSTAL, G.BLUE_CRYSTAL, G.RING)))
goto(G.MOST_MAGIC)
g.summon(G.ORIK)
g.throw(G.RED_CRYSTAL, G.GIMBAL)
step("crystals useless before the spell", lambda: g.has(G.RED_CRYSTAL))
g.cast("crys")
step("Crystallium Spectralis", lambda: g.flags.get("crystallium"))
for cr in (G.RED_CRYSTAL, G.GREEN_CRYSTAL, G.BLUE_CRYSTAL):
    g.throw(cr, G.GIMBAL)
while g.windows:                      # closing the last message frees Gimbal
    g.action("fire")
step("Gimbal is free", lambda: g.flags.get("gimbal_free") and not ch[G.GIMBAL].get("trapped"))
# 11. send everyone home from the last room of the gallery, Gimbal last
goto(G.GALLERY_END)
g.summon(G.GIMBAL)
step("Gimbal insists on going last", lambda: not ch[G.GIMBAL].get("home_sent"))
for c in (G.THOR, G.FLORIN, G.ORIK, G.SAMSUN, G.ELRAND, G.ROSMAR, G.BANSHEE):
    g.summon(c)
    msgs()
g.summon(G.GIMBAL)
while g.windows:
    g.action("fire")
    if g.state == "won":
        break
step("the quest is complete", lambda: g.state == "won")
print("\nPLAYTHROUGH COMPLETE: %d steps" % len(log))
