"""Sound effects and the title music, from the game's own SOUND/ files.

Everything is synthesised once from the samples, instruments and score
(cok/sound.py) and played through pygame's mixer. Without a sound device,
or with --mute, it stays silent. F8 mutes and unmutes.
"""
import sys
import threading
from array import array

import pygame

from cok import sound as S

# which of the game's sounds goes with what happens
SPELL_SOUNDS = {47: 'fireb', 51: 'light', 15: 'whisl', 79: 'light', 83: 'gate'}


class Audio:
    def __init__(self, files, muted=False):
        self.files = files
        self.muted = muted
        self.ok = False
        self.sounds = {}
        self.music = None
        if muted:
            return
        try:
            pygame.mixer.init(frequency=S.RATE, size=-16, channels=1)
            pygame.mixer.set_num_channels(12)
            self.format = pygame.mixer.get_init()        # what the device really gave us
            self.ok = True
        except pygame.error:
            return
        gf = files.gf
        if 'sound/sounddata' not in gf:
            self.ok = False
            return
        self.synth = S.Synth(S.read_bank(gf.read('sound/sounddata')),
                             lambda n: gf.read('sound/' + n) if 'sound/' + n in gf else None)

    def toggle(self):
        self.muted = not self.muted
        if self.ok and self.muted:
            pygame.mixer.stop()
        return self.muted

    def make(self, pcm):
        """A mixer Sound from 16-bit mono PCM at S.RATE, in the device's format."""
        freq, size, channels = self.format
        a = array('h')
        a.frombytes(pcm)
        if sys.byteorder != 'little':
            a.byteswap()
        if freq != S.RATE:
            n = int(len(a) * freq / S.RATE)
            ratio = S.RATE / freq
            a = array('h', (a[int(i * ratio)] for i in range(n)))
        if channels > 1:
            b = array('h', bytes(2 * len(a) * channels))
            for c in range(channels):
                b[c::channels] = a
            a = b
        if size not in (-16, 16):
            return None                                   # an 8-bit device: stay quiet
        return pygame.mixer.Sound(buffer=a.tobytes())     # native byte order, as the mixer wants

    def sound(self, name):
        if name not in self.sounds:
            inst = self.synth.find(name)
            pcm = S.to_pcm(self.synth.render(inst)) if inst is not None else b''
            self.sounds[name] = self.make(pcm) if pcm else None
        return self.sounds[name]

    def play(self, name):
        if not self.ok or self.muted:
            return
        try:
            snd = self.sound(name)
            if snd is not None:
                snd.play()
        except pygame.error:
            pass

    def play_music(self):
        """The title music, rendered in the background so the game starts at once."""
        if not self.ok or self.muted or 'sound/krynn' not in self.files.gf:
            return

        def work():
            try:
                pcm = S.render_music(self.files.gf.read('sound/krynn'), self.synth)
                self.music = self.make(pcm)
                if not self.muted:
                    self.music.play()
            except pygame.error:
                pass
        threading.Thread(target=work, daemon=True).start()

    # --- what happens in a fight -------------------------------------------------------
    def event(self, kind, what=None):
        if kind == 'hit':
            self.play('hit')
        elif kind == 'miss':
            self.play('swish')
        elif kind == 'shoot':
            self.play('arrow')
        elif kind == 'death':
            self.play(('dead0', 'dead1', 'dead', 'dead3', 'dead4')[hash(what) % 5])
        elif kind == 'cast':
            sid = getattr(what, 'id', 0)
            self.play(SPELL_SOUNDS.get(sid, 'spell' if getattr(what, 'cls', 'M') == 'C' else 'cast'))
        elif kind == 'level':
            self.play('turn')
