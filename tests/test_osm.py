import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient
from mapwalker.app import create_app
from mapwalker.osm import OSMContext,cell,distance_m,normalize

SAMPLE={'osm3s':{'timestamp_osm_base':'2026-09-29T00:00:00Z'},'elements':[
    {'type':'node','id':101,'lat':24.86,'lon':121.56,'tags':{'name':'測試峰','natural':'peak','ele':'1000'}},
    {'type':'way','id':202,'tags':{'name':'測試步道','highway':'path'},'geometry':[
        {'lon':121.55,'lat':24.86},{'lon':121.57,'lat':24.86}]},
    {'type':'node','id':303,'lat':24.9,'lon':121.6,'tags':{'historic':'ruins'}},
]}
RAW=json.dumps(SAMPLE,ensure_ascii=False).encode()


def test_background_cache_provenance_and_no_duplicate_fetch(tmp_path):
    osm=OSMContext(tmp_path)
    assert osm.context(121.56,24.86)['state']=='pending'
    calls=[]
    def fetch(query):calls.append(query);return RAW
    assert osm.once(fetch)
    result=osm.context(121.56,24.86)
    assert result['state']=='complete' and result['total']==2
    assert result['sha256']==hashlib.sha256(RAW).hexdigest()
    assert {f['properties']['osm_id'] for f in result['features']}=={101,202}
    assert all(f['properties']['distance_m']==0 for f in result['features'])
    assert result['features'][0]['properties']['url'].startswith('https://www.openstreetmap.org/')
    restarted=OSMContext(tmp_path)
    assert restarted.context(121.56,24.86)['sha256']==result['sha256']
    assert not restarted.once(fetch) and len(calls)==1


def test_geometry_uses_segments_and_never_bridges_missing_points():
    assert distance_m(dict(type='MultiLineString',coordinates=[[[121.55,24.86],[121.57,24.86]]]),121.56,24.86)==0
    data={'elements':[{'type':'way','id':1,'tags':{'highway':'path'},'geometry':[
        {'lon':121.50,'lat':24.86},{'lon':121.51,'lat':24.86},None,
        {'lon':121.59,'lat':24.86},{'lon':121.60,'lat':24.86}]}]}
    feature=normalize(data)[0]
    assert len(feature['geometry']['coordinates'])==2
    assert distance_m(feature['geometry'],121.55,24.86)>3000
    with pytest.raises(ValueError):normalize({'elements':[],'remark':'runtime error: timeout'})


def test_failed_request_has_backoff_and_preserves_previous_snapshot(tmp_path):
    osm=OSMContext(tmp_path);key,_,_=cell(121.56,24.86)
    osm.context(121.56,24.86);osm.once(lambda _:RAW)
    with osm.connect() as db:db.execute('UPDATE requests SET updated=? WHERE key=?',(time.time()-31*86400,key))
    assert osm.context(121.56,24.86)['state']=='pending'
    def fail(_):raise OSError('fixture network failure')
    osm.once(fail)
    result=osm.context(121.56,24.86)
    assert result['state']=='failed' and result['total']==2 and result['stale']
    assert result['retry_at']>time.time() and result['error']=='fixture network failure'
    assert not osm.once(fail)


def test_api_context_is_separate_from_detection_and_snapshot_is_reviewable(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[])
    with TestClient(app) as client:
        assert client.get('/api/osm/context',params={'lon':121.56,'lat':24.86}).json()['state']=='pending'
        app.state.osm.once(lambda _:RAW)
        result=client.get('/api/osm/context',params={'lon':121.56,'lat':24.86}).json()
        assert client.get('/api/osm/snapshot/'+result['sha256']).content==RAW
        assert client.get('/api/osm/snapshot/not-a-hash').status_code==404
        for values in [{'lon':'nan','lat':24.86},{'lon':0,'lat':24.86},{'lon':121.56,'lat':24.86,'radius':5000}]:
            assert client.get('/api/osm/context',params=values).status_code==422
        status=client.get('/api/status').json()
        assert status['candidates']==0 and status['tiles']==0 and status['counts']=={}


def test_modified_cached_evidence_is_detected(tmp_path):
    osm=OSMContext(tmp_path);osm.context(121.56,24.86);osm.once(lambda _:RAW)
    result=osm.context(121.56,24.86)
    (osm.root/'snapshots'/f"{result['sha256']}.json").write_bytes(b'{}')
    with pytest.raises(ValueError,match='hash mismatch'):osm.context(121.56,24.86)
