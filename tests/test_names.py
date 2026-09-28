import json
import pytest
from fastapi.testclient import TestClient
from mapwalker.app import create_app
from mapwalker.db import Store
from mapwalker.names import canonical_reading, match_name

BOUNDS=(121.5,24.8,121.6,24.9)
SOURCE='JM50K_1924_new'
SPEC=dict(fingerprint='names-fixture',name='text',version='test',config={},snapshot='test')

def seed(store,source=SOURCE,lon=121.55):
    store.enqueue(source,[(16,54896,28092)])
    job=store.claim()
    rows=[dict(kind='text',text=t,score=.8,lon=lon,lat=24.865,box=[10,10,30,30],disposition='candidate')
          for t in ['？ライ社','ウライ社','ウラィ社','桃園','????']]
    store.finish(job,rows,{},[])
    return store.pois(BOUNDS,source)['items']

@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC]);seed(app.state.store)
    with TestClient(app) as c:yield c,app.state.store

def test_question_mark_is_unknown_but_ro_and_mouth_are_literal():
    assert canonical_reading('？ライ社')=='?ライ社'
    assert canonical_reading('ロ口')=='ロ口'
    assert match_name('ロ','ウ') is None
    assert match_name('ウライ社','?ライ社')['reason']=='unknown-character'
    assert match_name('?ライ社','ウライ社')['reason']=='unknown-character'
    assert match_name('???','ウライ社') is None
    assert match_name('ウライ社','????') is None
    assert match_name('ウライ社','桃園') is None
    assert match_name('ウライ社','うらい社')['reason']=='exact'
    assert match_name('ウライ社','ｳﾗｲ社')['reason']=='exact'
    assert match_name('ウライ社','ウラィ社')['reason']=='similar-spelling'

def test_search_ranks_then_paginates_and_preserves_raw(client):
    c,store=client
    args=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,q='ウライ社',limit=1)
    first=c.get('/api/pois',params=args).json()
    assert first['total']==3 and first['items'][0]['text']=='ウライ社'
    second=c.get('/api/pois',params={**args,'offset':1}).json()['items'][0]
    assert second['text']=='？ライ社' and second['display_text']=='?ライ社'
    assert second['search_match']['suggested_name']=='ウライ社'
    assert second['search_match']['suggestion_source']=='Your search; unverified'
    assert store.poi(second['id'])['reading'] is None
    all_unknown=c.get('/api/pois',params={**args,'q':'???'}).json()
    assert all_unknown['total']==0 and 'known character' in all_unknown['search_message']
    short=c.get('/api/pois',params={**args,'q':'ライ社','limit':50}).json()
    assert all('suggested_name' not in p['search_match'] for p in short['items'])

def test_readings_append_preserve_raw_and_do_not_confirm_finding(client):
    c,store=client;p=store.pois(BOUNDS)['items'][0];pid=p['id']
    bad=c.post(f'/api/pois/{pid}/reading',json=dict(value='?ライ社',status='confirmed'))
    assert bad.status_code==400 and store.poi(pid)['readings']==[]
    assert c.post(f'/api/pois/{pid}/reading',json=dict(value='〓ライ社')).json()['value']=='?ライ社'
    assert c.post(f'/api/pois/{pid}/reading',json=dict(value='ウライ社',status='confirmed',origin='search-suggestion')).status_code==200
    restored=Store(store.path).poi(pid)
    assert restored['text']==p['text'] and restored['reading']=='ウライ社'
    assert [r['value'] for r in restored['readings']]==['?ライ社','ウライ社']
    assert restored['reviews']==[] and restored['disposition']=='candidate'
    assert c.post(f'/api/pois/{pid}/reading',json=dict(value='',status='confirmed')).status_code==400

def test_suggestions_are_local_provenanced_drafts_and_have_no_side_effects(client):
    c,store=client;pid=store.pois(BOUNDS)['items'][0]['id']
    suggestion=c.get(f'/api/pois/{pid}/suggestions',params={'q':'ウライ社'}).json()['items'][0]
    assert suggestion['name']=='ウライ社' and suggestion['origin']=='search-suggestion'
    assert suggestion['verified'] is False
    assert store.poi(pid)['readings']==[]
    assert c.get('/api/pois/999999/suggestions').status_code==404
    assert c.get(f'/api/pois/{pid}/suggestions',params={'q':'桃園'}).json()['items'][0]['source']=='Nearby OCR; unverified'

def test_search_respects_source_bounds_exclusion_and_versions(client):
    c,store=client;seed(store,'JM50K_1916')
    args=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,q='ウライ社')
    assert c.get('/api/pois',params=args).json()['total']==3
    assert c.get('/api/pois',params={**args,'bbox':'121.7,24.8,121.8,24.9'}).json()['total']==0
    pid=store.pois(BOUNDS,SOURCE)['items'][0]['id']
    with store.connect() as db:db.execute("UPDATE pois SET disposition='excluded' WHERE id=?",(pid,))
    assert c.get('/api/pois',params=args).json()['total']==2
    assert c.get('/api/pois',params={**args,'disposition':'all'}).json()['total']==3
    exported=c.get('/api/export',params=args).json()
    assert len(exported['features'])==2
    store.register([{**SPEC,'fingerprint':'next'}])
    assert c.get('/api/pois',params=args).json()['total']==0

def test_reading_override_and_explicit_rtl_alternative(client):
    c,store=client;pid=store.pois(BOUNDS)['items'][0]['id']
    store.save_reading(pid,'桃園')
    assert store.pois(BOUNDS,SOURCE,query='ウライ社')['total']==2
    with store.connect() as db:
        db.execute('UPDATE pois SET text=?,details=? WHERE id=?',('溪後桶',json.dumps({'reading_candidates':[{'text':'桶後溪','direction':'possible-right-to-left'}]}),pid))
    assert store.pois(BOUNDS,SOURCE,query='桶後溪')['total']==0
    store.save_reading(pid,'')
    result=store.pois(BOUNDS,SOURCE,query='桶後溪')
    assert result['total']==1 and result['items'][0]['text']=='溪後桶'
