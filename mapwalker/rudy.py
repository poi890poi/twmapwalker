"""Private, app-owned Mapsforge renderer and versioned viewer-only tiles."""
import atexit
import hashlib
import io
import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / 'styles/rudy/upstream/bochengsiong.xml'


def validate_tile(z, x, y):
    if not (5 <= z <= 19 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError('Tile coordinates or zoom outside Rudy source limits')


class RudyTiles:
    def __init__(self, data):
        self.root = Path(data) / 'rudy'
        self.mapfile = self.root / 'map/MOI_OSM_Taiwan_TOPO_Rudy.map'
        self.jar = self.root / 'mapsforgesrv.jar'
        self.lock = threading.Lock()
        self.process = None
        self.port = None
        self.version = None
        self.log = None
        atexit.register(self.close)

    def status(self):
        return dict(installed=self.mapfile.is_file() and self.jar.is_file() and THEME.is_file() and bool(shutil.which('java')),
                    attribution='Rudy / MOI.OSM Taiwan TOPO · OpenStreetMap contributors · Elevate / Tobias Kühn · bochengsiong',
                    style='bochengsiong maintained on current Rudy', min_zoom=5, max_zoom=19)

    def _start(self):
        if self.process and self.process.poll() is None:
            return
        if not self.status()['installed']:
            raise RuntimeError('Rudy layer is not installed. Run tools/setup-rudy.ps1 and install Java 17 or later.')
        if self.version is None:
            digest = hashlib.sha256()
            for path in [self.mapfile, self.jar, *sorted(THEME.parent.rglob('*'))]:
                if path.is_file() and path.suffix != '.json':
                    digest.update(path.name.encode())
                    with path.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024*1024), b''):
                            digest.update(chunk)
            self.version = digest.hexdigest()[:24]
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        config = self.root / 'renderer-config' / uuid.uuid4().hex
        (config / 'tasks').mkdir(parents=True)
        (config / 'server.properties').write_text(f'host=127.0.0.1\nport={self.port}\nrequestlog-format=\n', encoding='utf-8')
        # Java properties use forward slashes on Windows and need escaped backslashes.
        def prop(path):
            return str(path.resolve()).replace('\\', '/').replace(':', '\\:')
        for name, theme in [('rudy', THEME), ('upstream', THEME.parent / 'MOI_OSM.xml')]:
            (config / f'tasks/{name}.properties').write_text(
                f'mapfiles={prop(self.mapfile)}\nthemefile={prop(theme)}\nstyle=elmt-hiking\nlanguage=zh\n', encoding='utf-8')
        if self.log:
            self.log.close()
        self.log = (self.root / 'renderer.log').open('ab')
        self.process = subprocess.Popen([shutil.which('java'), '-Xmx512m', '-Djava.awt.headless=true', '-jar', str(self.jar.resolve()), '-c', str(config.resolve())],
            stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Rudy renderer stopped; inspect data/rudy/renderer.log')
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=.2):
                    return
            except OSError:
                time.sleep(.1)
        self.close()
        raise RuntimeError('Rudy renderer did not start within 30 seconds')

    def get(self, z, x, y):
        validate_tile(z, x, y)
        with self.lock:
            self._start()
            path = self.root / 'tiles' / self.version / str(z) / str(x) / f'{y}.png'
            if not path.is_file():
                url = f'http://127.0.0.1:{self.port}/{z}/{x}/{y}.png?task=rudy'
                with urllib.request.urlopen(url, timeout=45) as response:
                    payload = response.read(4_000_001)
                if len(payload) > 4_000_000:
                    raise RuntimeError('Unexpected Rudy tile size')
                with Image.open(io.BytesIO(payload)) as image:
                    image.load()
                    if image.size != (256, 256):
                        raise RuntimeError('Unexpected Rudy tile dimensions')
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                temporary.write_bytes(payload)
                temporary.replace(path)
            return path

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log:
            self.log.close()
            self.log = None
