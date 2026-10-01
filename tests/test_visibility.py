"""Hiding is reversible visibility, never a POI assessment or deletion."""
from test_names import client,BOUNDS,SOURCE,seed
from mapwalker.db import Store
import pytest


@pytest.mark.parametrize('classification',['other','noise'])
def test_classification_hides_existing_annotations_and_poi_restores(client,classification):
    c,store=client;pid=store.pois(BOUNDS)['items'][0]['id']
    # Existing annotations take effect too; hiding is derived, not a new write.
    store.save_annotation(pid,dict(classification=classification,ground_truth='Non-POI feature'))
    before=Store(store.path).poi(pid)
    assert before['hidden'] and before['visibility_history']==[]
    args=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,display='all')
    for endpoint in ('/api/browse','/api/pois','/api/export'):
        result=c.get(endpoint,params=args).json()
        ids={p['properties']['id'] for p in result['features']} if endpoint.endswith('export') else {p['id'] for p in result['items']}
        assert pid not in ids
    assert c.get('/api/browse',params={**args,'visibility':'hidden'}).json()['items'][0]['id']==pid
    restored=c.post(f'/api/pois/{pid}/annotation',json=dict(classification='poi',ground_truth='A POI',sync_reading=True))
    assert restored.status_code==200 and restored.json()['hidden'] is False
    assert pid in {p['id'] for p in c.get('/api/browse',params=args).json()['items']}
    assert Store(store.path).poi(pid)['annotations'][0]==before['annotations'][0]


def test_hide_restore_preserves_all_evidence_and_survives_restart(client):
    c,store=client;pid=store.pois(BOUNDS)['items'][0]['id']
    with store.connect() as db:db.execute("UPDATE pois SET kind='symbol' WHERE id=?",(pid,))
    c.post(f'/api/pois/{pid}/annotation',json=dict(ground_truth='Unknown symbol',note='May be significant'))
    store.review(pid,'uncertain','Investigate later')
    before=store.poi(pid)
    response=c.post(f'/api/pois/{pid}/visibility',json=dict(hidden=True))
    assert response.status_code==200
    hidden=Store(store.path).poi(pid)
    assert hidden['hidden'] and len(hidden['visibility_history'])==1
    for field in ('text','disposition','reading','readings','reviews','annotation','annotations','group_members'):
        assert hidden[field]==before[field]
    c.post(f'/api/pois/{pid}/visibility',json=dict(hidden=True))
    assert len(store.poi(pid)['visibility_history'])==1  # Idempotent retry.
    # Saving an annotation later must not silently restore visibility.
    c.post(f'/api/pois/{pid}/annotation',json=dict(ground_truth='Still unknown'))
    assert store.poi(pid)['hidden']
    assert c.post(f'/api/pois/{pid}/visibility',json=dict(hidden=False)).status_code==200
    restored=Store(store.path).poi(pid)
    assert not restored['hidden'] and len(restored['visibility_history'])==2
    assert restored['reviews']==before['reviews']


def test_visibility_agrees_across_list_map_counts_search_and_export(client):
    c,store=client;pid=store.pois(BOUNDS)['items'][0]['id']
    store.set_visibility(pid,True)
    args=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,display='all')
    for visibility,count in [('visible',4),('hidden',1),('all',5)]:
        result=c.get('/api/browse',params={**args,'visibility':visibility}).json()
        listed=c.get('/api/pois',params={**args,'visibility':visibility}).json()
        exported=c.get('/api/export',params={**args,'visibility':visibility}).json()
        assert result['total']==result['map']['total']==listed['total']==len(exported['features'])==count
        expected={p['id'] for p in result['items']}
        assert {p['id'] for p in result['map']['items']}==expected
        assert {p['properties']['id'] for p in exported['features']}==expected
        assert (pid in expected)==(visibility!='visible')
    assert c.get('/api/pois',params=args).json()['total']==4
    store.save_reading(pid,'Unique hidden name')
    assert c.get('/api/browse',params={**args,'q':'Unique hidden name'}).json()['total']==0
    assert c.get('/api/browse',params={**args,'q':'Unique hidden name','visibility':'hidden'}).json()['total']==1
    for display in ('top','reduced','adaptive'):
        assert all(p['id']!=pid for p in c.get('/api/browse',params={**args,'display':display}).json()['items'])


def test_only_explicit_members_change_and_invalid_requests_are_atomic(client):
    c,store=client;first,second,third=store.pois(BOUNDS)['items'][:3]
    ids=[p['id'] for p in (first,second,third)]
    url=f'/api/pois/{ids[0]}/visibility'
    assert c.post(url,json=dict(hidden=True,member_ids=ids[:2])).status_code==200
    assert store.poi(ids[0])['hidden'] and store.poi(ids[1])['hidden']
    assert not store.poi(ids[2])['hidden']
    other=seed(store,'JM50K_1916')[0]['id']
    for members in ([ids[0],999999],[ids[0],other]):
        assert c.post(url,json=dict(hidden=False,member_ids=members)).status_code==400
    assert store.poi(ids[0])['hidden'] and len(store.poi(ids[0])['visibility_history'])==1
    assert c.post('/api/pois/999999/visibility',json=dict(hidden=True)).status_code==404
    assert c.get('/api/browse',params=dict(bbox=','.join(map(str,BOUNDS)),visibility='bad')).status_code==422
