#!/usr/bin/env python3
"""Read the Journal Entries and Tavern Tales out of your scanned manual.

The game keeps much of its story in the printed manual ("you record it in
journal entry 51"). This turns your copy of the manual (a scanned PDF,
two pages per image) into a journal the remake can show in the game:

    extracted/journal/journal.json      {"journal": {"51": {...}}, "tavern": {...}}
    extracted/journal/img/*.png         maps and pictures that belong to an entry

    python3 tools/journal.py MANUAL.pdf [--pages 23-33] [--out extracted/journal]

Needs: pdfimages (poppler), tesseract, and Python's Pillow and numpy:
    macOS:  brew install poppler tesseract && pip3 install pillow numpy
The text is OCR'd, so it can have small mistakes; journal.json is plain
JSON and can be corrected by hand. Its "fixes" section is kept when the
tool runs again.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit('needs Pillow and numpy:  pip3 install pillow numpy')

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD_RE = re.compile(r'([Jj][a-z]{1,4}nal|[Jj][a-z]*al|Tav[a-z]*n)\s*(E[a-z]{2,4}|T[a-z]{2,3})\s*[\'"]?([0-9OoIlSB]{1,3})\b')
END_RE = re.compile(r'^\W*SPELLS\W*$')
SECTION_RE = re.compile(r'\s*\b(JOURNAL ENTRIES|TAVERN TALES)\b\s*')
UPSCALE = 2

# Figures in the SSI manual scan (PDF page, box as fractions of the spread,
# entry it belongs to). Figures are cropped as pictures and blanked out
# before the text is read. A different scan may need its own boxes.
FIGURES = [
    (24, (70, 345, 640, 740), ('journal', 13)),
    (24, (1062, 728, 1252, 936), ('journal', 18)),
    (25, (70, 662, 640, 928), ('journal', 23)),
    (27, (70, 683, 640, 937), ('journal', 45)),
    (28, (1088, 680, 1274, 888), ('journal', 62)),
    (29, (70, 118, 362, 560), ('journal', 63)),
    (30, (70, 112, 642, 562), ('journal', 72)),
    (31, (70, 112, 362, 502), ('journal', 81)),
    (31, (758, 122, 1012, 502), ('journal', 86)),
    (32, (358, 82, 642, 482), ('tavern', 0)),
    (33, (68, 82, 642, 472), ('tavern', 0)),
]
SCAN_W, SCAN_H = 1387, 974


def spreads(pdf, pages, tmp):
    """[(pdf page, image path)] of the scan (each image a two-page spread)."""
    subprocess.check_call(['pdfimages', '-j', '-f', str(pages[0]), '-l', str(pages[1]), pdf,
                           os.path.join(tmp, 'p')])
    files = sorted(n for n in os.listdir(tmp) if n.endswith('.jpg'))
    return [(pages[0] + i, os.path.join(tmp, n)) for i, n in enumerate(files)]


def columns(gray):
    """x ranges of the four text columns: split at the spine, then at each page's gutter."""
    h, w = gray.shape
    dark = gray[60:h - 30] < 140
    prof = dark.sum(axis=0)
    rows = dark.shape[0]
    cols = []
    for a, b in ((0, w // 2), (w // 2, w)):
        p = prof[a:b]
        # page edges and the spine shadow are solid ink columns: skip them
        xs = [i for i in range(len(p)) if 4 < p[i] < 0.35 * rows and 25 < i < len(p) - 25]
        if not xs:
            continue
        lo, hi = xs[0], xs[-1]
        band0 = lo + int(0.4 * (hi - lo))
        band = np.convolve(p[band0:lo + int(0.6 * (hi - lo))], np.ones(9), 'same')
        gx = band0 + int(np.argmin(band))
        cols += [(a + lo - 4, a + gx), (a + gx, a + hi + 5)]
    return cols


def ocr_lines(img):
    """[(text, left, top, height)] for every line tesseract finds."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'c.png')
        img.save(p)
        out = subprocess.run(['tesseract', p, 'stdout', '--psm', '4', 'tsv'],
                             capture_output=True, text=True, check=True).stdout
    lines = {}
    for row in out.splitlines()[1:]:
        f = row.split('\t')
        if len(f) < 12 or not f[11].strip() or float(f[10]) < 0:
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))
        x, y, h = int(f[6]), int(f[7]), int(f[9])
        e = lines.setdefault(key, [[], x, y, h])
        e[0].append(f[11])
        e[1], e[2], e[3] = min(e[1], x), min(e[2], y), max(e[3], h)
    return sorted(((' '.join(v[0]), v[1], v[2], v[3]) for v in lines.values()), key=lambda t: t[2])


def number(s):
    return int(s.translate(str.maketrans('OoIlSB', '001158')))


CLEAN = [(re.compile(r'[“”«»]'), '"'), (re.compile(r'[‘’`]'), "'"), (re.compile(r'\s+'), ' '),
         (re.compile(r'(?<=\w)\|(?=\w)'), 'l'), (re.compile(r'(?<![\w])\|(?![\w])'), 'I'),
         (re.compile(r'\s+([,.;:!?])'), r'\1')]


def clean(text):
    text = SECTION_RE.sub(' ', text)
    for rx, rep in CLEAN:
        text = rx.sub(rep, text)
    return text.strip()


def parse(pages, imgdir):
    """Walk columns in reading order; return {(kind, n): {'text': [...], 'images': [...]}}."""
    entries = {}
    cur = None
    para = []
    gaps = {}                       # (kind, n) -> [line gap before each paragraph]
    state = {'gap': 0.0, 'done': False}

    def close_para():
        if cur is not None and para:
            entries[cur]['text'].append(clean(' '.join(para)))
            gaps.setdefault(cur, []).append(state['gap'])
        para.clear()

    for page, path in pages:
        if state['done']:
            break
        src = Image.open(path)
        sx, sy = src.width / SCAN_W, src.height / SCAN_H
        gray = np.array(src.convert('L'))
        figs = [(tuple(int(v * f) for v, f in zip(box, (sx, sy, sx, sy))), who)
                for pg, box, who in FIGURES if pg == page]
        for fi, ((a, b, c, d), who) in enumerate(figs):
            e = entries.setdefault(who, {'text': [], 'images': []})
            name = '%s_%03d_%d.png' % (who[0], who[1], len(e['images']) + 1)
            src.crop((a, b, c, d)).save(os.path.join(imgdir, name))
            e['images'].append(name)
            gray[b:d, a:c] = 255
        cols = columns(gray)
        segments = []
        for half in (cols[0:2], cols[2:4]):
            if not half:
                continue
            hx0, hx1 = half[0][0], half[-1][1]
            # a figure as wide as the page: read both columns above it first
            cuts = sorted(b - 55 for (a, b, c, d), _ in figs
                          if (min(c, hx1) - max(a, hx0)) > 0.7 * (hx1 - hx0))
            bounds = [60] + [max(60, y) for y in cuts] + [gray.shape[0] - 20]
            for top, bottom in zip(bounds, bounds[1:]):
                segments += [(x0, x1, top, bottom) for x0, x1 in half]
        for x0, x1, top, bottom in segments:
            if state['done']:
                break
            col = gray[top:bottom, x0:x1]
            if col.shape[0] < 30:
                continue
            img = Image.fromarray(col).resize((col.shape[1] * UPSCALE, col.shape[0] * UPSCALE), Image.LANCZOS)
            lines = ocr_lines(img)
            # line pitch: the usual distance from one line's top to the next
            steps = sorted(b[2] - a[2] for a, b in zip(lines, lines[1:])
                           if 12 * UPSCALE < b[2] - a[2] < 35 * UPSCALE)
            lh = steps[len(steps) // 2] if steps else 20 * UPSCALE
            # left margin: where most lines start (a stray mark must not move it)
            xs = sorted(x for _, x, _, _ in lines) or [0]
            left = xs[len(xs) // 4]
            prev_bottom = None
            for text, x, y, _h in lines:
                if END_RE.match(text):
                    state['done'] = True
                    break
                m = HEAD_RE.search(text)
                if m and m.start() < 6:
                    close_para()
                    k = 'journal' if m.group(1).lower().startswith('j') else 'tavern'
                    n = number(m.group(3))
                    if cur is not None and cur[0] == k and not (cur[1] < n <= cur[1] + 3):
                        n = cur[1] + 1          # misread number: they run in order
                    cur = (k, n)
                    entries.setdefault(cur, {'text': [], 'images': []})
                    rest = text[m.end():].strip()
                    if rest:
                        para.append(rest)
                    state['gap'] = 0.0
                    prev_bottom = y + lh
                    continue
                if cur is None:
                    continue
                indent = x - left > 10 * UPSCALE
                gap = (y - prev_bottom) / float(lh) if prev_bottom is not None else 0.0
                if (indent or gap > 0.45) and para:
                    close_para()
                if not para:
                    state['gap'] = gap
                if para and para[-1].endswith('-') and not para[-1].endswith('--'):
                    para[-1] = para[-1][:-1] + text.split(' ', 1)[0]
                    rest = text.split(' ', 1)[1:] or ['']
                    if rest[0]:
                        para.append(rest[0])
                else:
                    para.append(text)
                prev_bottom = y + lh
    close_para()
    # a heading the scan lost: its text sits after a wide gap in the entry before
    for kind in ('journal', 'tavern'):
        nums = sorted(n for k, n in entries if k == kind and n > 0)
        for n in range(1, nums[-1] + 1 if nums else 1):
            prev = (kind, n - 1)
            if (kind, n) in entries or prev not in entries:
                continue
            g = gaps.get(prev, [])
            for i in range(1, len(g)):
                if g[i] > 1.6:
                    entries[(kind, n)] = {'text': entries[prev]['text'][i:], 'images': []}
                    entries[prev]['text'] = entries[prev]['text'][:i]
                    gaps[(kind, n)] = g[i:]
                    gaps[prev] = g[:i]
                    break
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('--pages', default='23-34', help='PDF pages (spreads) holding the journal and tales')
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'extracted', 'journal'))
    a = ap.parse_args()
    for tool in ('pdfimages', 'tesseract'):
        if not shutil.which(tool):
            sys.exit('needs %s (macOS: brew install poppler tesseract)' % tool)
    first, last = (int(v) for v in a.pages.split('-'))
    imgdir = os.path.join(a.out, 'img')
    os.makedirs(imgdir, exist_ok=True)
    out_json = os.path.join(a.out, 'journal.json')
    fixes = {}
    if os.path.exists(out_json):
        fixes = json.load(open(out_json)).get('fixes', {})
    with tempfile.TemporaryDirectory() as tmp:
        pages = spreads(a.pdf, (first, last), tmp)
        entries = parse(pages, imgdir)
    data = {'source': os.path.basename(a.pdf), 'journal': {}, 'tavern': {}, 'fixes': fixes}
    for (kind, n), e in sorted(entries.items()):
        data[kind][str(n)] = {'text': [p for p in e['text'] if p], 'images': e['images']}
    # hand corrections win: {"journal": {"8": {"text": [...]}}}
    for kind in ('journal', 'tavern'):
        for n, e in fixes.get(kind, {}).items():
            data[kind].setdefault(n, {'text': [], 'images': []}).update(e)
    with open(out_json, 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    for kind in ('journal', 'tavern'):
        nums = sorted(int(n) for n in data[kind] if int(n) > 0)
        missing = sorted(set(range(1, (nums[-1] if nums else 0) + 1)) - set(nums))
        print('%s: %d entries (1-%s)%s' % (kind, len(nums), nums[-1] if nums else 0,
                                          ', missing %s' % missing if missing else ''))
    print('->', os.path.relpath(out_json))


if __name__ == '__main__':
    main()
