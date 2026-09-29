from fastapi.testclient import TestClient
from mapwalker.app import create_app
from mapwalker.db import Store
from mapwalker.geo import lonlat

SOURCE='JM50K_1924_new'
SPECS=[dict(fingerprint=n,name=n,version='test',config={},snapshot='test') for n in ('first','second')]

def box(x=54896,y=28092):
    w,n=lonlat(x+.1,y+.1,16);e,s=lonlat(x+.9,y+.9,16)
    return [w,s,e,n]

def test_latest_view_preempts_backlog_after_current_check_and_survives_restart(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=SPECS);store=app.state.store
    store.enqueue(SOURCE,[(16,54896+i,28092) for i in range(20)])
    running=store.claim()
    with TestClient(app) as client:
        payload=dict(source=SOURCE,bbox=box(54915))
        r=client.post('/api/view',json=payload).json()
        assert r['added_jobs']==0 and r['area']['foreground']
        assert r['area']['working_elsewhere']
        assert client.post('/api/view',json=payload).json()['added_jobs']==0
        assert store.finish(running,[],{},[])
        restarted=Store(store.path)
        next_job=restarted.claim()
        assert next_job['x']==54915 and next_job['name']=='first'
        assert restarted.finish(next_job,[],{},[])
        # Revisiting an old tile overrides the just-promoted view.
        client.post('/api/view',json=dict(source=SOURCE,bbox=box()))
        assert restarted.claim()['x']==54896
        assert store.status()['tiles']==20

def test_source_switch_and_new_algorithm_keep_foreground(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=SPECS);s=app.state.store
    with TestClient(app) as c:
        assert c.post('/api/view',json=dict(source='JM50K_1916',bbox=box())).json()['added_jobs']==2
        c.post('/api/view',json=dict(source=SOURCE,bbox=box()))
        j=s.claim();assert j['source']==SOURCE;s.finish(j,[],{},[])
        s.register([dict(fingerprint='new',name='new',version='new',config={},snapshot='test')])
        j=s.claim();assert j['source']==SOURCE and j['algorithm']=='new'

def test_focus_preserves_pause_backoff_completed_and_failures(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=SPECS[:1]);s=app.state.store
    with TestClient(app) as c:
        c.post('/api/view',json=dict(source=SOURCE,bbox=box()))
        j=s.claim();s.finish(j,[],{},[])
        assert c.post('/api/view',json=dict(source=SOURCE,bbox=box())).json()['added_jobs']==0
        assert s.claim() is None
        c.post('/api/view',json=dict(source=SOURCE,bbox=box(54897)))
        j=s.claim();s.fail(j,'temporary')
        c.post('/api/view',json=dict(source=SOURCE,bbox=box(54897)))
        assert s.claim() is None  # View changes cannot bypass retry backoff.
        s.pause(True);assert s.claim(now=10**12) is None
        s.pause(False);j=s.claim(now=10**12);assert j['attempts']==2
        j['attempts']=3;s.fail(j,'permanent')
        c.post('/api/view',json=dict(source=SOURCE,bbox=box(54897)))
        assert s.claim(now=10**12) is None

def test_overview_no_mass_enqueue_and_invalid_bounds_no_mutation(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=SPECS)
    with TestClient(app) as c:
        r=c.post('/api/view',json=dict(source=SOURCE,bbox=[118,21.5,123,26.5]))
        assert r.status_code==200 and not r.json()['auto_queued']
        assert app.state.store.status()['tiles']==0
        assert c.post('/api/view',json=dict(source=SOURCE,bbox=[123,25,118,24])).status_code==400
        assert app.state.store.status()['tiles']==0
