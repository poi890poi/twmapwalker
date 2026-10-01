from test_names import client, BOUNDS, SOURCE
from mapwalker.db import Store


def test_annotations_persist_unicode_group_and_preserve_detection(client):
    c,store=client
    first,second,third=store.pois(BOUNDS)['items'][:3]
    url=f"/api/pois/{first['id']}/annotation"
    payload=dict(ground_truth='烏來社 שלום',classification='poi',map_direction='rtl',
                 fragment_ids=[second['id']],osm_type='node',osm_id=123,note='Read from right to left')
    assert c.post(url,json=payload).status_code==200
    restored=Store(store.path).poi(first['id'])
    assert restored['annotation']['ground_truth']==payload['ground_truth']
    assert restored['text']==first['text'] and restored['reviews']==[]
    group=restored['annotation']['group_id']
    assert group and store.poi(second['id'])['annotation']['group_id']==group
    payload.update(fragment_ids=[third['id']],classification='noise')
    assert c.post(url,json=payload).status_code==200
    assert store.poi(third['id'])['annotation']['group_id']==group
    assert store.poi(second['id'])['annotation']['group_id']==group
    assert len(store.poi(first['id'])['annotations'])==2
    assert store.poi(first['id'])['disposition']=='candidate'
    exported=c.get('/api/export',params=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,display='all')).json()
    feature=next(f for f in exported['features'] if f['properties']['id']==first['id'])
    assert feature['properties']['annotation']['classification']=='noise'


def test_invalid_annotation_is_atomic(client):
    c,store=client
    first=store.pois(BOUNDS)['items'][0]
    url=f"/api/pois/{first['id']}/annotation"
    assert c.post(url,json=dict(fragment_ids=[999999])).status_code==400
    assert c.post(url,json=dict(osm_type='way')).status_code==400
    assert c.post(url,json=dict(osm_id=-2,osm_type='node')).status_code==422
    assert c.post('/api/pois/999999/annotation',json={}).status_code==404
    assert store.poi(first['id'])['annotations']==[]
