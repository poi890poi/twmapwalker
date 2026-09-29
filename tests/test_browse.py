"""Selection and count invariants, using isolated synthetic findings only."""
import json

import pytest
from fastapi.testclient import TestClient
from mapwalker.app import create_app
from mapwalker.browse import map_features

SOURCE='JM50K_1924_new'
BOUNDS='121.5,24.8,121.6,24.9'
SPEC=dict(fingerprint='browse-fixture',name='text',version='test',config={},snapshot='test')


def seed(store, rows, source=SOURCE):
    store.enqueue(source,[(16,54896,28092)])
    job=store.claim()
    store.finish(job,rows,{},[])


def point(i, **kwargs):
    return dict(kind='text' if i%3==0 else 'trail' if i%3==1 else 'symbol',
                text=f'Name {i:04d}' if i%3==0 else '',score=.5,
                lon=121.55+(i%25)*.00001,lat=24.865+(i%17)*.00001,
                box=[10,10,30,30],disposition='candidate',**kwargs)


@pytest.fixture
def sample(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC])
    seed(app.state.store,[point(i) for i in range(137)])
    with TestClient(app) as client: yield client, app.state.store


def query(client, **params):
    r=client.get('/api/browse',params=dict(bbox=BOUNDS,source=SOURCE,**params))
    assert r.status_code==200,r.text
    return r.json()


def test_map_membership_independent_of_sort_and_page(sample):
    client,store=sample
    first=query(client,limit=25)
    expected={p['id'] for p in store.pois(tuple(map(float,BOUNDS.split(','))))['items']}
    assert first['total']==first['map']['total']==137
    for sort in ['priority','name','newest','score']:
        seen=[]
        for offset in range(0,137,25):
            result=query(client,limit=25,offset=offset,sort=sort)
            assert {p['id'] for p in result['map']['items']}==expected
            seen.extend(p['id'] for p in result['items'])
        assert len(seen)==len(set(seen))==137 and set(seen)==expected
    assert query(client,offset=9999,limit=25)['offset']==125


def test_latest_filters_export_and_map_agree(sample):
    client,store=sample
    p=store.pois((121.5,24.8,121.6,24.9))['items'][0]
    store.review(p['id'],'rejected','old');store.review(p['id'],'confirmed','latest')
    store.save_reading(p['id'],'?ライ社')
    args=dict(kind='text',review='confirmed',reading='named',q='ウライ社')
    result=query(client,**args)
    assert result['total']==result['map']['total']==1
    assert result['items'][0]['search_match']['suggested_name']=='ウライ社'
    exported=client.get('/api/export',params=dict(bbox=BOUNDS,source=SOURCE,**args)).json()
    assert [f['properties']['id'] for f in exported['features']]==[p['id']]
    assert query(client,review='rejected')['total']==0
    assert query(client,review='unreviewed')['total']==136
    assert query(client,reading='unread')['total']==91
    with store.connect() as db: db.execute("UPDATE pois SET disposition='excluded' WHERE id=?",(p['id'],))
    assert query(client,**args)['total']==0
    assert query(client,**args,disposition='all')['total']==1
    assert query(client,**args,disposition='excluded')['total']==1
    store.register([{**SPEC,'fingerprint':'next'}])
    assert query(client,disposition='all')['map']['total']==0


def test_crossing_trail_remains_visible_when_anchor_is_outside(sample):
    client,store=sample
    with store.connect() as db:
        pid=db.execute('SELECT MIN(id) FROM pois').fetchone()[0]
        geometry=dict(type='LineString',coordinates=[[121.49,24.85],[121.61,24.85]])
        db.execute('UPDATE pois SET kind=?,lon=?,lat=?,west=?,east=?,south=?,north=?,details=? WHERE id=?',
                   ('trail',121.49,24.85,121.49,121.61,24.85,24.85,json.dumps(dict(geometry=geometry)),pid))
    result=query(client,kind='trail')
    line=next(p for p in result['map']['items'] if p['id']==pid)
    assert line['geometry']==geometry and line['lon']==121.5
    assert store.poi(pid)['lon']==121.49


def test_dense_groups_preserve_every_finding_and_bound_payload():
    # 10,017 known fixture points, deliberately spread across many screen cells.
    rows=[dict(id=i,kind='symbol',text='',reading=None,details='{}',
               lon=118.1+(i%101)*.045,lat=21.6+(i//101)*.045,
               west=None,south=None,east=None,north=None,disposition='candidate') for i in range(10017)]
    result=map_features(rows,(118,21.5,123,26.5),19)
    assert result['total']==10017 and result['mode']=='groups'
    assert len(result['items'])<=2000
    assert sum(g['count'] for g in result['items'])==10017
    assert sum(g['kinds'].get('symbol',0) for g in result['items'])==10017
    for g in result['items']:
        assert g['bounds'][0]<=g['lon']<=g['bounds'][2]+1e-10
        assert g['bounds'][1]<=g['lat']<=g['bounds'][3]+1e-10


def test_fuzzy_search_has_no_first_twenty_thousand_cutoff(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC]);store=app.state.store
    rows=[dict(point(i),kind='text',text='山') for i in range(20005)]
    rows[-1]['text']='?ライ社';seed(store,rows)
    with TestClient(app) as client:
        result=query(client,q='ウライ社',limit=1)
    assert result['total']==result['map']['total']==1 and not result['search_truncated']
    assert result['items'][0]['text']=='?ライ社'


def test_invalid_inputs_and_matsu_navigation(sample):
    client,_=sample
    for arg in [dict(kind='bad'),dict(sort='DROP TABLE pois'),dict(review='bad'),
                dict(reading='bad'),dict(zoom=20),dict(limit=0),dict(offset=-1)]:
        assert client.get('/api/browse',params=dict(bbox=BOUNDS,**arg)).status_code==422
    for bbox in ['nan,24,122,25','122,24,121,25','121,24,125,25']:
        assert client.get('/api/browse',params=dict(bbox=bbox)).status_code==400
    assert client.get('/api/browse',params=dict(bbox='119.9,26.1,120,26.3')).status_code==200
    assert client.get('/api/coverage-summary',params=dict(bbox='119.9,26.1,120,26.3',source=SOURCE)).status_code==200
    assert client.post('/api/plan/estimate',json=dict(bbox=[119.95,26.15,119.96,26.16],sources=[SOURCE])).json()['allowed']


def test_source_filter_and_empty_query(sample):
    client,store=sample
    seed(store,[point(0)],'JM50K_1916')
    assert query(client)['total']==137
    assert query(client,q='???')['total']==0
    assert query(client,q='???')['search_message']
    result=client.get('/api/browse',params=dict(bbox=BOUNDS,source='JM50K_1916')).json()
    assert result['total']==result['map']['total']==1
