import asyncio
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from mapwalker.app import create_app
from mapwalker.live import LiveRevision


def test_revision_tracks_assets_and_only_loaded_python(tmp_path):
    for directory in ('web','mapwalker','styles/rudy/upstream','data'):
        (tmp_path/directory).mkdir(parents=True)
    py = tmp_path/'mapwalker/example.py'
    py.write_text('original')
    live = LiveRevision(tmp_path)
    original = live.current()
    (tmp_path/'data/results.json').write_text('new work')
    assert live.current() == original
    py.write_text('changed backend')
    assert live.current() == original
    assert LiveRevision(tmp_path).current() != original
    css = tmp_path/'web/new.css'
    css.write_text('body { color: red }')
    assert live.current() != original
    css.unlink()
    assert live.current() == original
    (tmp_path/'styles/rudy/enhancements.json').write_text('{}')
    assert live.current() != original


def test_live_mode_is_explicit_and_assets_revalidate(tmp_path):
    with TestClient(create_app(tmp_path/'off',worker_enabled=False,registry=[])) as client:
        assert client.get('/api/live-revision').json() == dict(enabled=False,revision=None)
    with TestClient(create_app(tmp_path/'on',worker_enabled=False,registry=[],live_reload=True)) as client:
        response = client.get('/api/live-revision')
        assert response.json()['enabled']
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/live-reload.js').headers['cache-control'] == 'no-cache'


def test_shutdown_waits_for_active_discovery_to_publish(tmp_path,monkeypatch):
    import mapwalker.app as module
    started, stopped, finish, published = (threading.Event() for _ in range(4))
    class InFlightWorker:
        def __init__(self,*args): self.stop=threading.Event()
        def run(self):
            started.set()
            self.stop.wait()
            stopped.set()
            finish.wait(5)
            published.set()
    monkeypatch.setattr(module,'Worker',InFlightWorker)
    app = create_app(tmp_path,registry=[])
    ended=threading.Event()
    def run():
        with TestClient(app): assert started.wait(2)
        ended.set()
    thread=threading.Thread(target=run)
    thread.start()
    try:
        assert stopped.wait(3)
        assert not ended.wait(.1)
        finish.set()
        assert ended.wait(3)
        assert published.is_set()
    finally:
        finish.set()
        thread.join(5)
