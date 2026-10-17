#!/usr/bin/env python3
"""Spellbound remake for macOS (Python 3 + pygame-ce).

    pip3 install pygame-ce
    python3 remake/bake.py path/to/S_BND128.TAP     # once: builds remake/data
    python3 remake/spellbound.py

Keys: arrows or N/M (walk), Up or A (jump), Space (command menu / select),
Esc (cancel), F5 save, F9 load, F2 music on/off, F11 full screen, Cmd+Q quit.
Testing: --headless --script "FRAME:ACTION ..." --shot FRAME:file.png
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser(description="Spellbound remake")
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--headless", action="store_true", help="no window/audio (testing)")
    ap.add_argument("--frames", type=int, default=0, help="stop after N frames")
    ap.add_argument("--script", default="", help="'FRAME:ACTION[:LEN] ...' actions: left right jump fire up down cancel")
    ap.add_argument("--shot", action="append", default=[], help="FRAME:file.png")
    args = ap.parse_args()

    if not os.path.exists(os.path.join(args.data, "game.json")):
        # first run: bake.py finds the TAP (or its .zip) itself and explains if it can't
        import subprocess
        if subprocess.call([sys.executable, os.path.join(HERE, "bake.py")]) != 0:
            sys.exit(1)

    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    import pygame
    from sbremake.assets import Assets
    from sbremake.game import Game

    pygame.init()
    flags = pygame.SCALED | (pygame.FULLSCREEN if args.fullscreen else 0)
    if args.headless:
        window = pygame.display.set_mode((320, 240))
    else:
        window = pygame.display.set_mode((320, 240), flags)
    pygame.display.set_caption("Spellbound")
    assets = Assets(args.data)
    game = Game(assets)

    music = assets.music and not args.no_music and not args.headless
    if music:
        try:
            pygame.mixer.music.load(assets.music)
            pygame.mixer.music.set_volume(0.6)
            pygame.mixer.music.play(-1)
        except pygame.error:
            music = False
    game.music_on = bool(music)

    script = []
    for item in args.script.split():
        parts = item.split(":")
        script.append((int(parts[0]), parts[1], int(parts[2]) if len(parts) > 2 else 1))
    shots = {int(s.split(":", 1)[0]): s.split(":", 1)[1] for s in args.shot}

    pad = None
    if not args.headless:
        pygame.joystick.init()
        if pygame.joystick.get_count():
            pad = pygame.joystick.Joystick(0)

    clock = pygame.time.Clock()
    frame = 0
    running = True
    keymap_action = {pygame.K_SPACE: "fire", pygame.K_RETURN: "fire", pygame.K_ESCAPE: "cancel",
                     pygame.K_BACKSPACE: "cancel", pygame.K_UP: "up", pygame.K_a: "up",
                     pygame.K_DOWN: "down", pygame.K_z: "down", pygame.K_F5: "save", pygame.K_F9: "load"}
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_q and ev.mod & pygame.KMOD_META:
                    running = False
                elif ev.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                elif ev.key == pygame.K_F2:
                    if assets.music and not args.headless:
                        game.music_on = not game.music_on
                        if game.music_on:
                            pygame.mixer.music.play(-1)
                        else:
                            pygame.mixer.music.stop()
                elif ev.key in keymap_action:
                    game.action(keymap_action[ev.key])
            elif ev.type == pygame.JOYBUTTONDOWN:
                game.action("fire" if ev.button == 0 else "cancel" if ev.button == 1 else "up")
            elif ev.type == pygame.JOYHATMOTION and ev.value[1]:
                game.action("up" if ev.value[1] > 0 else "down")

        keys = pygame.key.get_pressed()
        held = {
            "left": keys[pygame.K_LEFT] or keys[pygame.K_n],
            "right": keys[pygame.K_RIGHT] or keys[pygame.K_m],
            "jump": keys[pygame.K_UP] or keys[pygame.K_a],
        }
        if pad:
            hx = pad.get_hat(0)[0] if pad.get_numhats() else 0
            ax = pad.get_axis(0) if pad.get_numaxes() else 0
            held["left"] = held["left"] or hx < 0 or ax < -0.5
            held["right"] = held["right"] or hx > 0 or ax > 0.5
            held["jump"] = held["jump"] or (pad.get_numbuttons() > 2 and pad.get_button(2))
        for (f, act, n) in script:
            if act in ("left", "right", "jump"):
                if f <= frame < f + n:
                    held[act] = True
            elif f == frame:
                game.action(act)

        game.update(held)
        game.draw(window)
        if frame in shots:
            pygame.image.save(window, shots[frame])
        pygame.display.flip()
        frame += 1
        if args.frames and frame >= args.frames:
            running = False
        if not args.headless:
            clock.tick(50)
    pygame.quit()


if __name__ == "__main__":
    main()
