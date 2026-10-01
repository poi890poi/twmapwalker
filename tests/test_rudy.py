import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mapwalker.app import create_app
from mapwalker.rudy import RudyTiles, validate_tile
from mapwalker.rudy_style import build_style, NS

ROOT = Path(__file__).resolve().parents[1]


def test_theme_rebase_preserves_routing_semantics_and_resources(tmp_path):
    upstream = ROOT / 'styles/rudy/upstream/MOI_OSM.xml'
    output = tmp_path / 'style.xml'
    policy = json.loads((ROOT / 'styles/rudy/enhancements.json').read_text())
    report = build_style(upstream, output, policy)
    old, new = ET.parse(upstream), ET.parse(output)
    # Changing visibility must not remove current data predicates or difficulty/access keys.
    assert [r.attrib for r in old.iter('{'+NS+'}rule')] == [r.attrib for r in new.iter('{'+NS+'}rule')]
    before = list(old.iter('{'+NS+'}line'))
    after = list(new.iter('{'+NS+'}line'))
    assert len(before) == len(after)
    for a, b in zip(before, after):
        for name in ('stroke-dasharray', 'stroke-linecap', 'dy'):
            assert a.get(name) == b.get(name)
    assert report['counts']['trail_lines'] > 50
    assert report['counts']['water_lines'] > 0
    assert all(float(s.get('symbol-width','0')).is_integer() for s in new.iter('{'+NS+'}symbol'))
    assert output.read_bytes() == (ROOT / 'styles/rudy/upstream/bochengsiong.xml').read_bytes()
    assert 'Creative Commons Attribution-NonCommercial-ShareAlike' in output.read_text('utf-8')
    # Reapplying to unchanged upstream is deterministic.
    assert build_style(upstream, output, policy) == report


def test_rebase_rejects_changed_structure_or_missing_assets(tmp_path):
    theme = tmp_path / 'upstream.xml'
    theme.write_text('<rendertheme xmlns="'+NS+'"/>')
    policy = json.loads((ROOT / 'styles/rudy/enhancements.json').read_text())
    with pytest.raises(ValueError, match='structure changed'):
        build_style(theme, tmp_path/'out.xml', policy)
    theme.write_bytes((ROOT / 'styles/rudy/upstream/MOI_OSM.xml').read_bytes())
    with pytest.raises(ValueError, match='Missing theme asset'):
        build_style(theme, tmp_path/'out.xml', policy)


def test_rudy_is_viewer_only_and_bad_coordinates_never_start_renderer(tmp_path, monkeypatch):
    app = create_app(tmp_path, worker_enabled=False, registry=[])
    monkeypatch.setattr(app.state.rudy, 'get', lambda *args: pytest.fail('Invalid tile started renderer'))
    with TestClient(app) as client:
        assert client.get('/api/rudy/status').json()['installed'] is False
        assert client.get('/api/rudy/tiles/20/1/1').status_code == 400
        assert client.get('/api/rudy/tiles/15/-1/1').status_code == 400
        assert client.post('/api/plan', json={'bbox':[121.5,24.8,121.6,24.9], 'sources':['RUDY']}).status_code == 422
    rudy = RudyTiles(tmp_path)
    with pytest.raises(RuntimeError, match='not installed'):
        rudy.get(15,27449,14046)
    assert rudy.process is None
    rudy.close()


@pytest.mark.parametrize('tile', [(4,0,0),(19,2**19,0),(19,0,-1)])
def test_rudy_tile_limits(tile):
    with pytest.raises(ValueError):
        validate_tile(*tile)
