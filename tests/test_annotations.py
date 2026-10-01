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


def test_one_save_updates_search_status_and_exact_group_membership(client):
    c,store=client
    first,second,third=store.pois(BOUNDS)['items'][:3]
    ids=[p['id'] for p in (first,second,third)]
    url=f"/api/pois/{ids[0]}/annotation"
    payload=dict(ground_truth='烏來社 שלום',classification='poi',member_ids=ids,sync_reading=True,
                 osm_type='way',osm_id=42,osm_name='Modern name')
    assert c.post(url,json=payload).status_code==200
    for p in (first,second,third):
        saved=Store(store.path).poi(p['id'])
        assert saved['reading']==payload['ground_truth'] and saved['reading_status']=='confirmed'
        assert saved['text']==p['text'] and saved['disposition']==p['disposition']
        assert saved['reviews'][-1]['verdict']=='confirmed'
        assert {m['id'] for m in saved['group_members']}==set(ids)
    assert store.pois(BOUNDS,SOURCE,query='烏來社')['total']==3
    payload.update(member_ids=ids[:2],ground_truth='?來社',classification='noise',osm_type='',osm_id=None)
    assert c.post(url,json=payload).status_code==200
    assert store.poi(ids[0])['reading_status']=='tentative'
    assert store.poi(ids[1])['reviews'][-1]['verdict']=='rejected'
    assert store.poi(ids[1])['annotation']['osm_id'] is None
    removed=store.poi(ids[2])
    assert removed['annotation']['group_id'] is None
    assert removed['reading']=='烏來社 שלום'
    assert len(removed['annotations'])==2
    payload.update(member_ids=[ids[0]])
    assert c.post(url,json=payload).status_code==200
    assert store.poi(ids[0])['annotation']['group_id'] is None
    assert store.poi(ids[1])['annotation']['group_id'] is None


def test_invalid_group_does_not_partially_update_readings_or_reviews(client):
    from test_names import seed
    c,store=client
    pid=store.pois(BOUNDS,SOURCE)['items'][0]['id']
    other=seed(store,'JM50K_1916')[0]['id']
    for members in ([pid,999999],[pid,other]):
        response=c.post(f'/api/pois/{pid}/annotation',json=dict(
            ground_truth='完整名稱',classification='poi',sync_reading=True,member_ids=members))
        assert response.status_code==400
    saved=store.poi(pid)
    assert saved['annotations']==saved['readings']==saved['reviews']==[]


def test_osm_candidates_rank_names_aliases_and_geometry_without_writing(client):
    import json
    from mapwalker.annotations import rank_osm
    from mapwalker.osm import normalize,distance_m
    c,store=client
    raw={'elements':[
        {'type':'node','id':1,'lon':121.55,'lat':24.865,'tags':{'natural':'peak','name':'別山'}},
        {'type':'node','id':2,'lon':121.553,'lat':24.865,'tags':{'place':'village','name':'現代村','old_name:ja':'ウライ社'}},
        {'type':'way','id':3,'tags':{'highway':'path','name':'ウライ社步道'},'geometry':[
            {'lon':121.54,'lat':24.865},{'lon':121.56,'lat':24.865}]}]}
    features=normalize(raw)
    for f in features:f['properties']['distance_m']=round(distance_m(f['geometry'],121.55,24.865))
    ranked,enough=rank_osm(features,'ウライ社')
    assert enough and [f['properties']['osm_id'] for f in ranked]==[2,3,1]
    assert ranked[0]['properties']['matched_name']=='ウライ社'
    assert ranked[0]['properties']['match_reason']=='Name matches'
    assert rank_osm(features,'?ライ社')[0][0]['properties']['match_reason']=='Matches known characters'
    ranked,enough=rank_osm(features,'社')
    assert not enough and ranked[0]['properties']['distance_m']==0
    assert all(f['properties']['name_score'] is None for f in ranked)
    pid=store.pois(BOUNDS)['items'][0]['id']
    url=f'/api/pois/{pid}/osm-suggestions'
    assert c.get(url).json()['state']=='pending'
    c.app.state.osm.once(lambda _:json.dumps(raw).encode())
    result=c.get(url,params={'q':'ウライ社'}).json()
    assert result['features'][0]['properties']['osm_id']==2
    assert result['sha256'] and result['text_used']
    assert store.poi(pid)['annotations']==store.poi(pid)['readings']==[]
    assert c.get('/api/pois/999999/osm-suggestions').status_code==404
