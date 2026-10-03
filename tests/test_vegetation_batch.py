import json
import pytest
from mapwalker.db import Store
from mapwalker.vegetation_batch import VegetationBatch


class Service:
    def __init__(self):self.calls=0
    def inspect(self,item):
        self.calls+=1
        return dict(status='candidate',matches=[{'box':[1,2,3,4]}],preview='data:image/png;base64,test')


def setup(tmp_path,n=3,profile='test'):
    store=Store(tmp_path/'mapwalker.sqlite3')
    store.register([dict(fingerprint='batch-test',name='text',version='test',config={},snapshot='test')])
    store.enqueue('JM50K_1916',[(16,54886,28100)]);job=store.claim()
    store.finish(job,[dict(kind='text',text='Keep raw text',score=.9,lon=121.5,lat=24.8,box=[10,10,30,40],details={},disposition='candidate') for _ in range(n)],{},[])
    batch=VegetationBatch(store,tmp_path,service=Service(),profile=(profile,{}))
    return store,batch


def snapshot(store):
    with store.connect() as db:
        return {table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in ('pois','annotations','reviews','readings','poi_visibility')}


def test_readonly_scan_cache_numeric_errors_and_resume(tmp_path):
    store,batch=setup(tmp_path,105);before=snapshot(store)
    def interrupt(_):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):batch.scan(interrupt)
    assert batch.summary()['run']['processed']==100
    assert batch.summary()['run']['state']=='interrupted'
    done=batch.scan();assert done['run']['processed']==105 and done['run']['state']=='complete'
    assert batch.service.calls==105 and snapshot(store)==before
    batch.scan();assert batch.service.calls==105
    assert batch.pending(limit=24)['next_after']==24
    assert len(batch.pending(after=24,limit=100)['items'])==81
    batch.profile='second-version'
    def numeric(_):return {'status':'numeric-context','matches':[],'numeric_readings':[{'text':'98'}]}
    batch.service.inspect=numeric;batch.scan();assert not batch.pending()['items']
    assert batch.summary()['checks']=={'numeric-context':105}
    batch.profile='third-version'
    def missing(_):raise ValueError('Original evidence input hash mismatch')
    batch.service.inspect=missing;batch.scan()
    assert batch.summary()['checks']=={'error':105} and not batch.pending()['items']
    assert snapshot(store)==before


def test_existing_manual_work_and_late_edits_always_win(tmp_path):
    store,batch=setup(tmp_path,6)
    with store.connect() as db:
        db.execute("INSERT INTO annotations VALUES(NULL,1,?,1)",(json.dumps({'classification':'poi','note':'keep'}),))
        db.execute("INSERT INTO reviews VALUES(NULL,2,'confirmed','keep',1)")
        db.execute("INSERT INTO readings VALUES(NULL,3,'Keep name','confirmed','manual',1)")
        db.execute("INSERT INTO poi_visibility VALUES(NULL,4,0,1)")
    before=snapshot(store);batch.scan();assert batch.service.calls==2
    items=batch.pending()['items'];assert [r['id'] for r in items]==[5,6]
    with store.connect() as db:db.execute("INSERT INTO readings VALUES(NULL,6,'New manual edit','tentative','manual',2)")
    before=snapshot(store)
    with pytest.raises(ValueError,match='changed'):batch.decide(batch.profile,items,'other')
    assert snapshot(store)==before # Even the first valid selection must not be saved.
    assert [r['id'] for r in batch.pending()['items']]==[5]
    batch.decide(batch.profile,[items[0]],'other')
    assert store.poi(5)['hidden'] and store.poi(5)['annotation']['classification']=='other'
    with store.connect() as db:
        assert db.execute('SELECT text FROM pois WHERE id=5').fetchone()[0]=='Keep raw text'
        assert not db.execute('SELECT 1 FROM readings WHERE poi_id=5').fetchone()


def test_input_version_dismissal_and_atomic_rollback(tmp_path):
    store,batch=setup(tmp_path);batch.scan();items=batch.pending()['items']
    with pytest.raises(ValueError,match='Method changed'):batch.decide('old-version',items,'other')
    with store.connect() as db:db.execute("UPDATE pois SET box='[0,0,5,5]' WHERE id=2")
    assert [r['id'] for r in batch.pending()['items']]==[1,3]
    with pytest.raises(ValueError,match='changed'):batch.decide(batch.profile,items,'other')
    before=snapshot(store);batch.decide(batch.profile,[items[0]],'dismiss');assert snapshot(store)==before
    assert [r['id'] for r in batch.pending()['items']]==[3]
    with store.connect() as db:
        db.execute("CREATE TRIGGER reject_review BEFORE INSERT ON reviews BEGIN SELECT RAISE(ABORT,'test rollback'); END")
    with pytest.raises(Exception,match='test rollback'):batch.decide(batch.profile,[items[2]],'other')
    assert snapshot(store)==before


def test_api_contract_and_validation(tmp_path):
    from fastapi.testclient import TestClient
    from mapwalker.app import create_app
    spec=dict(fingerprint='batch-test',name='text',version='test',config={},snapshot='test')
    store,batch=setup(tmp_path)
    app=create_app(tmp_path,worker_enabled=False,registry=[spec]);batch=app.state.vegetation_batch
    batch.service=Service();batch.scan()
    with TestClient(app) as client:
        response=client.get('/api/vegetation-review?limit=2');assert response.status_code==200
        page=response.json();assert len(page['items'])==2
        payload=dict(profile=page['profile'],items=[{'id':r['id'],'input_key':r['input_key']} for r in page['items']],outcome='other')
        assert client.post('/api/vegetation-review/decisions',json=payload,headers={'Origin':'https://elsewhere.invalid'}).status_code==403
        assert not store.poi(1)['hidden']
        assert client.post('/api/vegetation-review/decisions',json=payload).json()['saved']==2
        assert store.poi(1)['hidden'] and store.poi(2)['hidden']
        assert client.post('/api/vegetation-review/decisions',json=payload).status_code==409
        assert client.post('/api/vegetation-review/decisions',json={**payload,'items':[]}).status_code==422
        assert client.get('/api/vegetation-review?limit=101').status_code==422


def test_live_lease_blocks_second_scanner_and_stale_lease_is_recovered(tmp_path):
    import time
    store,batch=setup(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO vegetation_runs(profile,metadata,owner,state,ceiling,total,created,updated) VALUES('older','{}','old-owner','running',3,3,?,?)",(time.time(),time.time()))
    with pytest.raises(ValueError,match='already running'):batch.scan()
    with store.connect() as db:db.execute('UPDATE vegetation_runs SET updated=0')
    assert batch.scan()['run']['state']=='complete'
    with store.connect() as db:assert db.execute("SELECT state FROM vegetation_runs WHERE profile='older'").fetchone()[0]=='interrupted'


def test_viewer_current_advice_and_manual_precedence(tmp_path):
    store,batch=setup(tmp_path,6)
    assert batch.viewer_evidence([1])=={1:{'status':'unchecked'}}
    before=snapshot(store);batch.scan()
    assert batch.viewer_evidence([1])[1]['status']=='candidate'
    items=batch.pending()['items'];batch.decide(batch.profile,[items[0]],'dismiss')
    with store.connect() as db:
        db.execute("UPDATE pois SET box='[0,0,5,5]' WHERE id=2")
        db.execute("INSERT INTO reviews VALUES(NULL,3,'confirmed','keep',1)")
        db.execute("UPDATE vegetation_checks SET status='numeric-context',evidence=? WHERE poi_id=4",(json.dumps({'status':'numeric-context'}),))
        db.execute("UPDATE vegetation_checks SET status='error',evidence='{}' WHERE poi_id=5")
    advice=batch.viewer_evidence(range(1,7))
    assert 1 not in advice and 3 not in advice
    assert advice[2]['status']==advice[5]['status']=='unchecked'
    assert advice[4]['status']=='numeric-context' and advice[6]['status']=='candidate'
    result=dict(total=6,items=[dict(id=i) for i in range(1,7)],map=dict(mode='groups',items=[dict(count=5),dict(count=1,item=dict(id=6))]))
    decorated=batch.decorate_view(result)
    assert decorated['total']==6 and [p['id'] for p in decorated['items'] if p['possible_vegetation']]==[6]
    assert decorated['map']['items']==[dict(count=5),dict(count=1,item=dict(id=6,possible_vegetation=True))]
    assert batch.service.calls==6 # Browse/detail lookup never runs OCR.
    batch.profile='new-method'
    assert batch.viewer_evidence([6])=={6:{'status':'unchecked'}}
    assert not batch.decorate_view(dict(items=[dict(id=6)]))['items'][0]['possible_vegetation']


def test_viewer_api_reuses_checked_evidence_without_changing_annotations(tmp_path):
    from fastapi.testclient import TestClient
    from mapwalker.app import create_app
    spec=dict(fingerprint='batch-test',name='text',version='test',config={},snapshot='test')
    store,batch=setup(tmp_path)
    app=create_app(tmp_path,worker_enabled=False,registry=[spec]);batch=app.state.vegetation_batch
    batch.service=Service();batch.scan();before=snapshot(store)
    def unexpected(_):raise AssertionError('Cached evidence must not run OCR')
    app.state.vegetation_evidence.inspect=unexpected
    with TestClient(app) as client:
        assert client.get('/api/pois/1').json()['vegetation_evidence']['status']=='candidate'
        assert client.get('/api/pois/1/vegetation-evidence').json()['status']=='candidate'
        result=client.get('/api/browse?bbox=121.49,24.79,121.51,24.81&display=all&zoom=19').json()
        assert result['total']==3 and all(p['possible_vegetation'] for p in result['items'])
        assert all(p['possible_vegetation'] for p in result['map']['items'])
        assert snapshot(store)==before
        item=batch.pending()['items'][0];batch.decide(batch.profile,[item],'dismiss')
        assert client.get('/api/pois/1').json()['vegetation_evidence'] is None
