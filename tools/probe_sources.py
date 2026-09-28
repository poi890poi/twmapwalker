"""Download a small named source sample; no detection or evaluation labels."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mapwalker.geo import world
from mapwalker.paths import default_data
from mapwalker.sources import TileCache, SOURCES

root = Path(__file__).resolve().parents[1]
cache = TileCache(default_data())
records = []
for name, lon, lat in [('town', 121.550, 24.865), ('mountain', 121.574, 24.846)]:
    x, y = map(int, world(lon, lat, 16))
    for source in SOURCES:
        path, meta, _ = cache.get(source, 16, x, y)
        records.append(dict(name=name, path=str(path), **meta))
        print(name, source, x, y, meta['bytes'], flush=True)
(root / 'evidence' / 'source-probe.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), 'utf-8')
