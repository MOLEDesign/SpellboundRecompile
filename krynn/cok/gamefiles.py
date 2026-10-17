"""Find and read the game's files from the user's own copy.

Accepts any of: the downloaded .zip of ADF images, a folder of .adf images,
or a folder of already extracted files (e.g. a hard disk install). Files are
looked up case-insensitively by name; when several disks carry the same
file the first disk wins (they are identical copies).
"""
import os
import zipfile

from .adf import ADF

SEARCH = ('original', '.', '..', os.path.expanduser('~/Downloads'))


class GameFiles:
    def __init__(self, source=None):
        self.files = {}           # lower name -> bytes
        self.disks = []
        self.source = source or self.find()
        if not self.source:
            raise FileNotFoundError(
                'Champions of Krynn not found: put your .zip or .adf files in krynn/original/')
        self._load(self.source)
        if 'game' not in self.files:
            raise FileNotFoundError('no Champions of Krynn disk 1 (file "game") in %s' % self.source)

    @staticmethod
    def find():
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for d in SEARCH:
            d = os.path.join(here, d) if not os.path.isabs(d) else d
            if not os.path.isdir(d):
                continue
            names = sorted(os.listdir(d))
            for n in names:
                if n.lower().endswith('.zip') and 'krynn' in n.lower():
                    return os.path.join(d, n)
            if any(n.lower().endswith('.adf') for n in names) or 'game' in names:
                if any('krynn' in n.lower() or n.lower() == 'game' or n.lower().startswith('ecl') for n in names):
                    return d
        return None

    def _load(self, src):
        images = []
        if os.path.isfile(src) and src.lower().endswith('.zip'):
            with zipfile.ZipFile(src) as z:
                for n in sorted(z.namelist()):
                    if n.lower().endswith('.adf'):
                        images.append((n, z.read(n)))
        elif os.path.isfile(src):
            images.append((src, open(src, 'rb').read()))
        else:
            for root, _, names in os.walk(src):
                for n in sorted(names):
                    p = os.path.join(root, n)
                    if n.lower().endswith('.adf'):
                        images.append((p, open(p, 'rb').read()))
                    elif not n.lower().endswith('.zip'):
                        rel = os.path.relpath(p, src).replace(os.sep, '/')
                        self.files.setdefault(rel.lower(), open(p, 'rb').read())
        for name, data in images:
            adf = ADF(data)
            self.disks.append(adf.label)
            for path, content in adf.files():
                self.files.setdefault(path.lower(), content)

    def __contains__(self, name):
        return name.lower() in self.files

    def read(self, name):
        try:
            return self.files[name.lower()]
        except KeyError:
            raise FileNotFoundError(name)

    def names(self):
        return sorted(self.files)
