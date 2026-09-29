"""Keep immutable viewer cache hits independent of slow upstream downloads."""
from .sources import TileCache, tile_url


class ViewerTiles:
    def __init__(self, cache):
        self.cache = cache

    def get(self, source, z, x, y):
        tile_url(source, z, x, y)  # Validate before constructing a filesystem path.
        record = self.cache.root / source / str(z) / str(x) / f'{y}.json'
        if record.is_file():
            # Published records are immutable and atomically installed. An independent
            # reader retains the original SHA-256 check without waiting for a miss.
            reader = TileCache(self.cache.root.parent.parent, snapshot=self.cache.root.name)
            return reader.get(source, z, x, y)
        # Preserve download throttling, single flight and all input validation.
        return self.cache.get(source, z, x, y)
