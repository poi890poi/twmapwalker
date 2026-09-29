import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from mapwalker.sources import TileCache
from mapwalker.viewer_tiles import ViewerTiles


def test_cached_tile_served_while_unrelated_download_is_blocked(tmp_path, monkeypatch):
    cache = TileCache(tmp_path, interval=0)
    viewer = ViewerTiles(cache)
    folder = cache.root / 'JM50K_1924_new/15/27448'
    folder.mkdir(parents=True)
    payload = b'immutable cached bytes'
    path = folder / '14046.png'
    path.write_bytes(payload)
    meta = dict(file=path.name, sha256=hashlib.sha256(payload).hexdigest())
    (folder / '14046.json').write_text(json.dumps(meta))
    started, release = Event(), Event()

    def slow_download(*args, **kwargs):
        started.set()
        assert release.wait(5)
        raise OSError('controlled upstream failure')

    monkeypatch.setattr('mapwalker.sources.urllib.request.urlopen', slow_download)
    with ThreadPoolExecutor(2) as pool:
        missing = pool.submit(viewer.get, 'JM50K_1924_new', 15, 27449, 14046)
        try:
            assert started.wait(2)
            hit = pool.submit(viewer.get, 'JM50K_1924_new', 15, 27448, 14046)
            assert hit.result(timeout=1) == (path, meta, True)
            assert not missing.done()
        finally:
            release.set()
        with pytest.raises(OSError, match='controlled upstream'):
            missing.result()
    # Independent reading must not weaken evidence integrity or input validation.
    path.write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='integrity'):
        viewer.get('JM50K_1924_new', 15, 27448, 14046)
    with pytest.raises(ValueError):
        viewer.get('JM50K_1924_new', 99, 1, 1)
