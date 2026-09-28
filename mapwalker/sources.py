"""Verified source definitions and immutable, content-addressed tile cache."""
import hashlib
import io
import json
import shutil
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

SOURCES = {
    'JM50K_1916': dict(title='1916 蕃地地形圖', format='jpg', min_zoom=5, max_zoom=16,
                       attribution='中央研究院 人社中心 GIS 專題中心'),
    'JM50K_1924_new': dict(title='1924 陸地測量部 · 新版高解析度', format='png', min_zoom=5, max_zoom=16,
                           attribution='中央研究院 人社中心 GIS 專題中心'),
    'EMAP': dict(title='現代 NLSC 通用電子地圖', format='jpg', min_zoom=5, max_zoom=19,
                 attribution='內政部國土測繪中心'),
}
HISTORICAL = ('JM50K_1916', 'JM50K_1924_new')
# Change this to a NEW identifier to fetch a new immutable imagery snapshot.
SNAPSHOT = '2026-09-28-v1'


def tile_url(source, z, x, y):
    item = SOURCES[source]
    if not (item['min_zoom'] <= z <= item['max_zoom'] and 0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError('Tile coordinates or zoom outside source limits')
    if source == 'EMAP':
        return f'https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}'
    return f'https://gis.sinica.edu.tw/tileserver/file-exists.php?img={source}-{item["format"]}-{z}-{x}-{y}'


class TileCache:
    def __init__(self, root, snapshot=SNAPSHOT, interval=0.4):
        self.root = Path(root) / 'tiles' / snapshot
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.next_fetch = 0
        self.interval = interval

    def get(self, source, z, x, y):
        url = tile_url(source, z, x, y)
        folder = self.root / source / str(z) / str(x)
        record = folder / f'{y}.json'
        with self.lock:
            if record.exists():
                meta = json.loads(record.read_text('utf-8'))
                path = folder / meta['file']
                payload = path.read_bytes()
                if hashlib.sha256(payload).hexdigest() != meta['sha256']:
                    raise ValueError(f'Cache integrity failure: {path}')
                return path, meta, True
            time.sleep(max(0, self.next_fetch - time.monotonic()))
            if shutil.disk_usage(self.root).free < 16_000_000:
                raise ValueError('Less than 16 MB free on the data drive; choose a data folder with more space')
            self.next_fetch = time.monotonic() + self.interval
            request = urllib.request.Request(url, headers={'User-Agent': 'Mapwalker/0.1 local research (rate limited)'})
            start = time.perf_counter()
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = response.read(4_000_001)
                content_type = response.headers.get('Content-Type', '')
                final_url = response.geturl()
            if len(payload) > 4_000_000 or not content_type.startswith('image/'):
                raise ValueError(f'Unexpected tile response: {content_type}')
            with Image.open(io.BytesIO(payload)) as img:
                img.load()
                if img.size != (256, 256):
                    raise ValueError(f'Unexpected tile dimensions: {img.size}')
                # Transparent no-data must not masquerade as an empty discovery run.
                if 'A' in img.getbands() and img.getchannel('A').getextrema()[1] == 0:
                    raise ValueError('Source returned a transparent no-data tile')
            digest = hashlib.sha256(payload).hexdigest()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'{y}-{digest[:16]}.{SOURCES[source]["format"]}'
            self._atomic(path, payload)
            meta = dict(source=source, z=z, x=x, y=y, url=url, final_url=final_url,
                        fetched_at=time.time(), sha256=digest, file=path.name,
                        content_type=content_type, bytes=len(payload), download_ms=(time.perf_counter()-start)*1000)
            self._atomic(record, json.dumps(meta, ensure_ascii=False, indent=2).encode())
            return path, meta, False

    @staticmethod
    def _atomic(path, payload):
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_bytes(payload)
        temp.replace(path)

    def mosaic(self, source, z, x, y, pad=64):
        """3x3 context, cropped to one owner tile plus a halo. All inputs required."""
        canvas = Image.new('RGB', (768, 768), 'white')
        manifest = []
        io_start = time.perf_counter()
        decode_ms = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                path, meta, cached = self.get(source, z, x+dx, y+dy)
                start = time.perf_counter()
                with Image.open(path) as im:
                    # Composite partial alpha onto white, not black.
                    rgba = im.convert('RGBA')
                    rgb = Image.new('RGB', im.size, 'white')
                    rgb.paste(rgba, mask=rgba.getchannel('A'))
                    canvas.paste(rgb, ((dx+1)*256, (dy+1)*256))
                decode_ms += (time.perf_counter()-start)*1000
                manifest.append({**meta, 'cache_hit': cached})
        elapsed = (time.perf_counter()-io_start)*1000
        return canvas.crop((256-pad, 256-pad, 512+pad, 512+pad)), manifest, dict(io_ms=elapsed-decode_ms, decode_ms=decode_ms)
