import pytest
from fastapi.testclient import TestClient

from mapwalker.app import create_app
from mapwalker.geo import lonlat

SOURCE='JM50K_1924_new'
TILE=(16,54896,28092)
w,n=lonlat(54896.1,28092.1,16)
e,s=lonlat(54896.9,28092.9,16)
BBOX=[w,s,e,n]
SPECS=[dict(fingerprint=name,name=name,version='test',config={},snapshot='test') for name in ('first','second')]


@pytest.fixture
def area(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=SPECS)
    with TestClient(app) as client:yield client,app.state.store


def progress(client):
    r=client.get('/api/coverage-summary',params=dict(source=SOURCE,bbox=','.join(map(str,BBOX))))
    assert r.status_code==200,r.text
    return r.json()


def plan(client):
    r=client.post('/api/plan',json=dict(sources=[SOURCE],bbox=BBOX))
    assert r.status_code==200,r.text
    return r.json()


def test_duplicate_queued_is_not_complete_and_partial_checks_are_visible(area):
    client,store=area
    assert progress(client)['state']=='not_queued'
    assert plan(client)['added_jobs']==2
    repeated=plan(client)
    assert repeated['added_jobs']==0 and 'Not finished yet' in repeated['message']
    assert repeated['areas'][0]['state']=='queued'
    job=store.claim();running=progress(client)
    assert running['checks']['running']==1 and running['current']['name']=='first'
    assert running['current']['elapsed_seconds']>=0
    assert store.finish(job,[],{},[])
    partial=progress(client)
    assert partial['checks']['percent']==50 and partial['complete']==0
    assert partial['checks']['pending']==1
    assert store.finish(store.claim(),[],{},[])
    done=progress(client)
    assert done['state']=='complete' and done['checks']['percent']==100 and done['complete']==1
    repeated=plan(client)
    assert 'no text/symbol candidates detected' in repeated['message']
    assert 'Not finished' not in repeated['message']


def test_failed_and_paused_checks_never_report_finished(area):
    client,store=area
    plan(client);store.pause(True)
    assert progress(client)['state']=='paused'
    assert 'paused' in plan(client)['message']
    store.pause(False)
    store.finish(store.claim(),[],{},[])
    job=store.claim();job['attempts']=3;store.fail(job,'fixture source failed')
    failed=progress(client)
    assert failed['state']=='failed' and failed['checks']['failed']==1
    assert failed['checks']['percent']==50 and failed['complete']==0
    assert 'retry failures' in plan(client)['message']
    store.pause(True)
    assert 'retry failures' in plan(client)['message']


def test_findings_count_only_published_text_symbols_in_view(area):
    client,store=area
    plan(client)
    p=dict(kind='text',text='山',score=.9,lon=(w+e)/2,lat=(s+n)/2,box=[0,0,20,20],disposition='candidate',details={})
    store.finish(store.claim(),[p,{**p,'kind':'trail'},{**p,'disposition':'excluded'},
                                {**p,'lon':e+.1}],{},[])
    value=progress(client)
    assert value['findings']==dict(candidates=1,excluded=1)
    assert value['checks']['complete']==1 and value['state']=='queued'
    # Published results are accessible before all algorithms finish the tile.
    rows=client.get('/api/browse',params=dict(source=SOURCE,bbox=','.join(map(str,BBOX)),include_trails=False)).json()
    assert rows['total']==1


def test_work_elsewhere_and_expired_lease_are_explicit(area):
    client,store=area
    store.enqueue('JM50K_1916',[TILE]);job=store.claim()
    plan(client)
    value=progress(client)
    assert value['state']=='queued' and value['working_elsewhere']
    store.finish(job,[],{},[]);store.finish(store.claim(),[],{},[])
    job=store.claim(lease=-1)
    assert progress(client)['state']=='interrupted'
