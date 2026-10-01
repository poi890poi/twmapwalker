"""Small file revisions for live viewer updates; data and evidence are never watched."""
import hashlib
from pathlib import Path

from .paths import ROOT


def signature(paths):
    records = []
    for path in sorted(paths):
        try:
            stat = path.stat()
            records.append((str(path), stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            records.append((str(path), None, None))
    return hashlib.sha256(repr(records).encode()).hexdigest()


def style_inputs(root=ROOT):
    folder = root / 'styles/rudy'
    return [folder/'enhancements.json', *[p for p in (folder/'upstream').rglob('*')
            if p.is_file() and p.suffix != '.tmp' and p.name not in ('bochengsiong.xml','bochengsiong.build.json')]]


class LiveRevision:
    def __init__(self, root=ROOT):
        self.root = root
        # Do not announce Python edits until the new server has actually loaded them.
        self.backend = signature((root/'mapwalker').rglob('*.py'))

    def current(self):
        assets = [p for p in (self.root/'web').rglob('*') if p.is_file()]
        return hashlib.sha256((self.backend + signature(assets + style_inputs(self.root))).encode()).hexdigest()
