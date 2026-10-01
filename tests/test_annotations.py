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
    exported=c.get('/api/export',params=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,display='all',visibility='all')).json()
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


def test_other_survives_restart_filters_groups_and_reclassification(client):
    c,store=client
    original=store.pois(BOUNDS)['items'][:2]
    ids=[p['id'] for p in original]
    with store.connect() as db:db.execute("UPDATE pois SET kind='symbol' WHERE id=?",(ids[1],))
    url=f'/api/pois/{ids[0]}/annotation'
    payload=dict(ground_truth='圖幅接合表',classification='other',member_ids=ids,sync_reading=True)
    assert c.post(url,json=payload).status_code==200
    for p in original:
        saved=Store(store.path).poi(p['id'])
        assert saved['annotation']['classification']=='other'
        assert saved['reviews'][-1]['verdict']=='other'
        assert saved['reading']=='圖幅接合表' and saved['text']==p['text']
        assert saved['disposition']==p['disposition'] and saved['hidden']
        assert {m['id'] for m in saved['group_members']}==set(ids)
    args=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,display='all',review='other',visibility='hidden')
    browse=c.get('/api/browse',params=args).json()
    assert {p['id'] for p in browse['items']}==set(ids)
    assert {p['id'] for p in browse['map']['items']}==set(ids)
    assert c.get('/api/pois',params=args).json()['total']==2
    exported=c.get('/api/export',params=args).json()['features']
    assert {f['properties']['id'] for f in exported}==set(ids)
    assert all(f['properties']['annotation']['classification']=='other' for f in exported)
    assert c.get('/api/browse',params={**args,'review':'rejected'}).json()['total']==0
    assert c.get('/api/browse',params={**args,'review':'uncertain'}).json()['total']==0
    assert c.get('/api/browse',params={**args,'visibility':'visible'}).json()['total']==0
    # Reclassifying restores both pieces, even with a legacy manual hide record.
    store.set_visibility(ids[0],True)
    payload['classification']='poi'
    assert c.post(url,json=payload).status_code==200
    restored=Store(store.path).poi(ids[0])
    assert not restored['hidden'] and restored['reviews'][-1]['verdict']=='confirmed'
    assert [a['payload']['classification'] for a in restored['annotations']]==['other','poi']
    assert c.get('/api/browse',params={**args,'visibility':'all'}).json()['total']==0
    assert c.get('/api/browse',params={**args,'visibility':'visible','review':'confirmed'}).json()['total']==2


def test_other_is_not_suggested_as_a_poi_name(client):
    c,store=client
    first,second=store.pois(BOUNDS)['items'][:2]
    store.save_reading(first['id'],'圖幅?合表')
    store.save_reading(second['id'],'圖幅接合表')
    assert any(p['poi_id']==second['id'] for p in store.name_suggestions(first['id'])['items'])
    assert c.post(f"/api/pois/{second['id']}/annotation",json=dict(
        ground_truth='圖幅接合表',classification='other',sync_reading=True)).status_code==200
    assert all(p['poi_id']!=second['id'] for p in store.name_suggestions(first['id'])['items'])


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
        assert (saved['annotation']['osm_type'],saved['annotation']['osm_id'],saved['annotation']['osm_name'])==('way',42,'Modern name')
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


def test_osm_link_replacement_unlink_and_failed_save_preserve_history(client):
    c,store=client
    pid=store.pois(BOUNDS)['items'][0]['id'];url=f'/api/pois/{pid}/annotation'
    for kind,object_id,name in [('node',123,'同名地點'),('relation',123,'同名地點')]:
        response=c.post(url,json=dict(osm_type=kind,osm_id=object_id,osm_name=name))
        assert response.status_code==200
        saved=Store(store.path).poi(pid)['annotation']
        assert (saved['osm_type'],saved['osm_id'],saved['osm_name'])==(kind,object_id,name)
    # A failed replacement must not alter the saved association.
    assert c.post(url,json=dict(osm_type='way',osm_id=456,member_ids=[999999])).status_code==400
    assert Store(store.path).poi(pid)['annotation']['osm_type']=='relation'
    exported=c.get('/api/export',params=dict(bbox=','.join(map(str,BOUNDS)),source=SOURCE,display='all')).json()
    link=next(f for f in exported['features'] if f['properties']['id']==pid)['properties']['annotation']
    assert (link['osm_type'],link['osm_id'],link['osm_name'])==('relation',123,'同名地點')
    assert c.post(url,json=dict(osm_type='',osm_id=None,osm_name='')).status_code==200
    restored=Store(store.path).poi(pid)
    assert restored['annotation']['osm_type']=='' and restored['annotation']['osm_id'] is None
    assert [(a['payload']['osm_type'],a['payload']['osm_id']) for a in restored['annotations']]==[('node',123),('relation',123),('',None)]


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
