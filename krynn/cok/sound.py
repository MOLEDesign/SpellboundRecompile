"""The game's sound: IFF 8SVX samples, SoundX instruments and envelopes, and
the SMUS title music, rendered to 16-bit PCM.

Files in SOUND/ on disk 1:

  arrow, cast2, dead, fireb, gate, hit, swish, pad, pad2, cast3samp,
  lightsamp, tuningfork, whislsamp2   8SVX samples
  cast3, cast4                        INST instruments
  krynn                               SMUS score (the title music)
  sounddata                           the instrument bank: NAME + FORM pairs of
                                      8SVX waveforms (square, saw, tri, odd,
                                      odd2), ENVL envelopes and INST instruments
  periodtable                         note periods for the player

The bank is written without IFF padding (chunks of odd length are not
followed by a pad byte).

INST: PTCH (pitch envelope), VLUM (volume envelope) and SAMP (sample) by
name. ENVL: (ticks, value) byte pairs, one tick being 1/50 s:

    volume  value = level to reach (0-64) over the ticks
    pitch   value = signed change of the Amiga period over the ticks
    ff 02 hi lo   set the period to hi*256+lo
    ff 01         hold the value
    ff 00         end (a volume envelope ending stops the sound)
    fe n          loop back n pairs (ff 02 counts as two)

SMUS: SHDR tempo (128ths of a quarter note per minute), volume, tracks;
INS1 instruments (register 0.. named in1 ... in7, found in the bank);
TRAK events (id, data): id 0-127 a note (MIDI number), 128 rest,
129 instrument; for notes and rests data bit 7 = chord, bit 6 = tied,
bits 5-4 = tuplet, bit 3 = dotted, bits 2-0 = division (0 whole ... 6).
"""
import struct
from array import array

CLOCK = 3546895            # Amiga PAL clock: sample rate = CLOCK / period
TICK = 50                  # envelope ticks per second
RATE = 22050               # output sample rate


# --- IFF ----------------------------------------------------------------------------
def chunks(data, off=0, end=None, pad=True):
    end = len(data) if end is None else end
    while off + 8 <= end:
        cid = data[off:off + 4]
        n = struct.unpack('>I', data[off + 4:off + 8])[0]
        yield cid, data[off + 8:off + 8 + n]
        off += 8 + n + ((n & 1) if pad else 0)


FIB = (-34, -21, -13, -8, -5, -3, -2, -1, 0, 1, 2, 3, 5, 8, 13, 21)


class Sample:
    """An 8SVX sound: signed 8-bit samples, with its one-shot and loop parts."""

    def __init__(self, data):
        body = data[12:] if data[:4] == b'FORM' else (data[4:] if data[:4] == b'8SVX' else data)
        vh = raw = None
        for pad in (True, False):                       # the bank leaves out IFF padding
            for cid, b in chunks(body, 0, pad=pad):
                if cid == b'VHDR':
                    vh = b
                elif cid == b'BODY':
                    raw = b
            if vh is not None and raw is not None:
                break
        (self.one_shot, self.repeat, self.per_cycle, self.rate, self.octaves,
         comp) = struct.unpack('>IIIHBB', vh[:16])
        self.volume = struct.unpack('>I', vh[16:20])[0] / 65536.0 if len(vh) >= 20 else 1.0
        if comp == 1:                                   # Fibonacci-delta
            out, v = [], raw[1] if len(raw) > 1 else 0
            for byte in raw[2:]:
                for nib in (byte >> 4, byte & 15):
                    v = (v + FIB[nib]) & 0xFF
                    out.append(v)
            raw = bytes(out)
        self.data = array('b', bytes(raw))
        self.octaves = max(1, self.octaves)

    def octave(self, k):
        """(samples, one-shot length, loop length) of octave k (0 = the highest)."""
        n1, n2 = self.one_shot << k, self.repeat << k
        start = sum((self.one_shot + self.repeat) << i for i in range(k))
        return self.data[start:start + n1 + n2], n1, n2


def read_bank(data):
    """sounddata -> {name: Sample | envelope bytes | instrument dict}."""
    out, name = {}, None
    for cid, body in chunks(data, 0, pad=False):
        if cid == b'NAME':
            name = body.split(b'\0')[0].decode('latin-1')
        elif cid == b'FORM' and name:
            out[name] = parse_form(body)
    return out


def parse_form(body):
    kind = body[:4]
    if kind == b'8SVX':
        return Sample(body)
    if kind == b'ENVL':
        return bytes(body[4:])
    if kind == b'INST':
        return {cid.decode(): v.split(b'\0')[0].decode('latin-1') for cid, v in chunks(body, 4, pad=False)}
    return None


# --- envelopes ------------------------------------------------------------------------
def envelope(env, start, absolute, ticks):
    """Values tick by tick (and whether the sound ends at the last one).

    absolute: volume envelopes give targets, pitch envelopes changes."""
    values, v, i = [], float(start), 0
    pairs = [env[k:k + 2] for k in range(0, len(env) - 1, 2)]
    ended, loops = False, 0
    while len(values) < ticks and i < len(pairs):
        a, b = pairs[i][0], pairs[i][1]
        if a == 0xFF:
            if b == 2 and i + 1 < len(pairs):          # set the period
                v = float(pairs[i + 1][0] << 8 | pairs[i + 1][1])
                i += 2
                continue
            if b == 0:
                ended = True
            break                                       # hold (01) or end (00)
        if a == 0xFE:
            loops += 1
            if loops > 1000:
                break
            i = max(0, i - b)
            continue
        target = b if absolute else v + (b - 256 if b > 127 else b)
        steps = max(1, a) if a else 0
        if steps == 0:
            v = float(target)
        else:
            d = (target - v) / steps
            for _ in range(steps):
                v += d
                values.append(v)
        i += 1
    if not values:
        values.append(v)
    if ended:
        return values, True
    while len(values) < ticks:
        values.append(values[-1])
    return values[:max(ticks, 1)], False


# --- synthesis ------------------------------------------------------------------------
def note_hz(n):
    return 440.0 * 2 ** ((n - 69) / 12.0)


class Synth:
    """Renders instruments of a bank (and loose SOUND/ files) to PCM."""

    def __init__(self, bank, loader=None):
        self.bank = bank
        self.loader = loader            # name -> bytes of SOUND/<name>, or None
        self.cache = {}

    def find(self, name):
        if name in self.bank:
            return self.bank[name]
        if name not in self.cache:
            data = self.loader(name.lower()) if self.loader else None
            self.cache[name] = parse_form(data[8:]) if data and data[:4] == b'FORM' else None
        return self.cache[name]

    def render(self, inst, seconds=None, note=None, volume=1.0):
        """Samples (floats -1..1) of an instrument; a note (MIDI) for the music,
        else the sample's own pitch. seconds: how long the note is held."""
        if isinstance(inst, str):
            inst = self.find(inst)
        if isinstance(inst, Sample):
            inst = {'SAMP': inst}
        smp = inst['SAMP'] if isinstance(inst['SAMP'], Sample) else self.find(inst['SAMP'])
        if smp is None:
            return []
        # pick the octave and the period
        if note is not None and smp.per_cycle:
            hz = note_hz(note)
            k = smp.octaves - 1                         # the finest copy of the wave
            data, n1, n2 = smp.octave(k)
            period = CLOCK / (hz * (smp.per_cycle << k))
        else:
            data, n1, n2 = smp.octave(0)
            period = CLOCK / max(1, smp.rate)
        if not len(data):
            return []
        vol_env = self.find(inst['VLUM']) if inst.get('VLUM') else None
        per_env = self.find(inst['PTCH']) if inst.get('PTCH') else None
        if seconds is not None:
            held = seconds
        elif not n2:
            held = (n1 + n2) / max(1.0, CLOCK / period) + 0.1      # a one-shot sample
        else:
            held = 6.0 if vol_env else 2.0      # a loop: until its volume envelope ends
        ticks = max(1, int(held * TICK) + 1)
        vols, vend = envelope(vol_env, 0, True, ticks) if vol_env else ([64.0] * ticks, False)
        if seconds is None and n2 and not vend:
            vols = vols[:2 * TICK]                       # a held loop: two seconds
        pers, _ = envelope(per_env, period, False, len(vols)) if per_env else ([period] * len(vols), False)
        per_tick = RATE // TICK
        out = []
        pos = 0.0
        size = len(data)
        for t, vol in enumerate(vols):
            step = CLOCK / max(60.0, pers[min(t, len(pers) - 1)]) / RATE
            amp = vol / 64.0 * volume * smp.volume / 128.0
            for _ in range(per_tick):
                i = int(pos)
                if i >= size:
                    if not n2:
                        return out                      # a one-shot sample ran out
                    pos = n1 + (pos - n1) % n2
                    i = int(pos)
                out.append(data[i] * amp)
                pos += step
        if not vend and seconds is not None:
            fade = min(len(out), RATE // 100)           # no click at a note's end
            for k in range(fade):
                out[-1 - k] *= k / fade
        return out


DIVISION = (4.0, 2.0, 1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125)
TUPLET = (1.0, 2.0 / 3, 4.0 / 5, 6.0 / 7)


def read_smus(data):
    """-> (quarters per minute, {register: instrument name}, [[(time, note or None,
    length, register)] per track]) with times and lengths in quarter notes."""
    tempo, insts, tracks = 120.0, {}, []
    for cid, body in chunks(data, 12):
        if cid == b'SHDR':
            tempo = struct.unpack('>H', body[:2])[0] / 128.0
        elif cid == b'INS1':
            insts[body[0]] = body[4:].split(b'\0')[0].decode('latin-1')
        elif cid == b'TRAK':
            notes, t, reg = [], 0.0, 0
            last = {}
            for k in range(0, len(body) - 1, 2):
                sid, d = body[k], body[k + 1]
                if sid == 129:
                    reg = d
                    continue
                if sid > 128:
                    continue
                length = DIVISION[d & 7] * (1.5 if d & 8 else 1.0) * TUPLET[(d >> 4) & 3]
                if sid < 128:
                    if sid in last and last[sid][1]:           # tied: lengthen the last one
                        idx = last[sid][0]
                        tt, nn, ll, rr = notes[idx]
                        notes[idx] = (tt, nn, ll + length, rr)
                    else:
                        notes.append((t, sid, length, reg))
                        last[sid] = (len(notes) - 1, False)
                    last[sid] = (last[sid][0], bool(d & 0x40))
                if not d & 0x80:                               # a chord note keeps the time
                    t += length
            tracks.append(notes)
    return tempo, insts, tracks


def render_music(smus, synth):
    """The score mixed to 16-bit mono PCM bytes at RATE."""
    tempo, insts, tracks = read_smus(smus)
    spq = 60.0 / tempo                                  # seconds per quarter note
    end = max((t + ln for tr in tracks for t, n, ln, r in tr), default=0) * spq + 2
    mix = [0.0] * int(end * RATE)
    voices = max(1, len(tracks))
    for tr in tracks:
        for t, n, ln, reg in tr:
            name = insts.get(reg)
            inst = synth.find(name) if name else None
            if inst is None:
                continue
            wave = synth.render(inst, ln * spq, n, 1.0 / voices ** 0.5)
            at = int(t * spq * RATE)
            for k, v in enumerate(wave):
                if at + k < len(mix):
                    mix[at + k] += v
    return to_pcm(mix)


def to_pcm(samples, gain=0.9):
    peak = max(1e-6, max((abs(v) for v in samples), default=0))
    scale = 32767 * gain / max(1.0, peak)
    out = array('h', (int(max(-32768, min(32767, v * scale))) for v in samples))
    if struct.pack('=h', 1) != struct.pack('<h', 1):
        out.byteswap()
    return out.tobytes()


def wav(pcm, rate=RATE):
    """A mono 16-bit WAV file around PCM bytes."""
    return (b'RIFF' + struct.pack('<I', 36 + len(pcm)) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16) + b'data' +
            struct.pack('<I', len(pcm)) + pcm)
