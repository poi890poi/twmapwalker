import json
import math
import pytest

from fastapi.testclient import TestClient
from mapwalker.app import create_app
from mapwalker.display import choose, context_bounds, priority, CELL_PIXELS
from mapwalker.geo import world, lonlat

SOURCE='JM50K_1924_new'
SPEC=dict(fingerprint='display-fixture',name='text',version='test',config={},snapshot='test')
X,Y=(math.floor(v*256/CELL_PIXELS)*CELL_PIXELS for v in world(121.55,24.86,15))


def row(i,x=30,y=30,score=.9,text='溪',kind='text',details=None):
    lon,lat=lonlat((X+x)/256,(Y+y)/256,15)
    return dict(id=i,kind=kind,text=text,score=score,details=json.dumps(details or {}),
                box='[0,0,32,32]',lon=lon,lat=lat,west=None,east=None,south=None,north=None,
                source=SOURCE,disposition='candidate')


def bounds(x0=0,x1=256):
    w,n=lonlat((X+x0)/256,Y/256,15);e,s=lonlat((X+x1)/256,(Y+128)/256,15)
    return w,s,e,n


def test_levels_nested_and_adaptive_keeps_more_of_sparse_cells():
    dense=[row(i,x=20+i,score=.7+i/100) for i in range(10)]
    sparse=row(20,x=150,score=.8,text='unknown Latin')
    noise=row(21,x=160,score=.99,text='500')
    rows=dense+[sparse,noise]
    top,t=choose(rows,bounds(),15,'top');reduced,r=choose(rows,bounds(),15,'reduced');adaptive,a=choose(rows,bounds(),15,'adaptive')
    assert set(top)<=set(reduced) and set(top)<=set(adaptive)
    assert len(top)==1 and len(reduced)==5 and len(adaptive)==3
    assert 20 in adaptive and 21 not in adaptive
    assert t['available']==r['available']==a['available']==12
    assert a['hidden']==9


def test_ranking_does_not_require_or_use_manual_labels():
    raw=row(1,text='',score=.95)
    assert priority(raw)>=.74 # unread region still eligible
    assert priority({**raw,'review':'rejected','reading':'ウライ社','reading_status':'confirmed'})==priority(raw)
    assert priority(row(2,text='500',score=.99))<.38
    assert priority(row(3,kind='trail',details={'dash_count':8}))>=.74
    assert priority(row(4,kind='symbol',details={'fill':.4,'area':200,'similar_components':30}))<.38
    assert priority(row(5,kind='symbol',details={'fill':.4,'area':410,'similar_components':1}))>=.73


def test_thin_contour_symbols_keep_lower_tiers_without_top_priority():
    # Actual annotated contour geometry, including the previous trail-context bonus.
    contour=row(1,kind='symbol',text='',details=dict(area=481,fill=481/(42*59),
                                                   similar_components=1,trail_context=True))
    contour['box']='[0,0,42,59]'
    assert priority(contour)==.58
    assert priority({**contour,'reading':'known name','review':'confirmed'})==.58
    for level in ['reduced','adaptive']:
        assert set(choose([contour],bounds(),15,level)[0])=={1}
    assert choose([contour],bounds(),15,'top')[0]=={}
    # Sparse character near the cutoff: the rejected .15 trial lost this shape.
    character=row(2,kind='symbol',text='',details=dict(area=640,fill=.256,similar_components=1))
    character['box']='[0,0,50,50]'
    assert round(priority(character),6)==.74
    # CRAFT mark regions, OCR and junctions have separate evidence rules.
    region={**contour,'kind':'text','details':dict(profile='synthetic-map-v1',support_angles=[0,90])}
    assert priority(region)==.80
    junction={**contour,'details':dict(junction_count=4,area=481)}
    assert priority(junction)==.50


def test_contour_cap_is_scale_and_translation_invariant():
    base=row(1,kind='symbol',text='',details=dict(area=200,fill=.25,similar_components=1))
    base['box']='[-5,10,15,50]'
    scaled={**base,'box':'[20,30,60,110]',
            'details':dict(area=800,fill=.25,similar_components=1)}
    assert priority(base)==priority(scaled)==.58


def test_contour_ranking_keeps_all_candidates_and_shared_view_selection(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC]);store=app.state.store
    store.enqueue(SOURCE,[(16,54896,28092)]);job=store.claim()
    contour=row(1,kind='symbol',text='',details=dict(area=481,fill=481/(42*59),similar_components=1))
    contour['box']='[0,0,42,59]'
    known=row(2,x=150,text='山')
    for p in [contour,known]:
        p.pop('id');p.pop('source');p['box']=json.loads(p['box']);p['details']=json.loads(p['details'])
    store.finish(job,[contour,known],{},[])
    base=dict(bbox=','.join(map(str,bounds())),source=SOURCE,display_zoom=15)
    with TestClient(app) as client:
        for level,count in [('top',1),('reduced',2),('adaptive',2),('all',2)]:
            args={**base,'display':level}
            result=client.get('/api/browse',params=args).json()
            assert result['total']==result['map']['total']==count
            assert len(client.get('/api/export',params=args).json()['features'])==count
        assert store.pois(bounds(),kind='symbol')['total']==1


def test_deterministic_rank_and_complete_cell_pan_context():
    rows=[row(i,x=20+i,score=.9) for i in range(10)]
    assert choose(rows,bounds(),15,'top')[0]==choose(reversed(rows),bounds(),15,'top')[0]
    a=context_bounds(bounds(10,110),15);b=context_bounds(bounds(15,115),15)
    assert a==b
    # Outside winner still occupies its cell; a tiny pan cannot promote weaker clutter.
    outside=row(99,x=120,score=1)
    assert choose(rows+[outside],bounds(10,110),15,'top')[0]=={}
    assert choose(rows+[outside],bounds(15,115),15,'top')[0]=={}


def test_selection_shared_by_map_list_export_and_pages(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC]);store=app.state.store
    store.enqueue(SOURCE,[(16,54896,28092)]);job=store.claim()
    rows=[row(i,x=20+i,score=.7+i/100) for i in range(10)]+[row(20,x=150,text='山')]
    for p in rows:
        p.pop('id');p.pop('source');p['box']=json.loads(p['box']);p['details']=json.loads(p['details'])
    store.finish(job,rows,{},[])
    base=dict(bbox=','.join(map(str,bounds())),source=SOURCE,display_zoom=15)
    with TestClient(app) as client:
        all_rows=client.get('/api/browse',params=base).json();assert all_rows['total']==11
        for level in ['top','reduced','adaptive']:
            args={**base,'display':level}
            first=client.get('/api/browse',params={**args,'limit':1}).json()
            expected={p['id'] for p in first['map']['items']}
            assert first['total']==first['map']['total']==first['display']['shown']
            assert first['display']['available']==11
            for sort in ['priority','newest','name','score']:
                seen=[]
                for offset in range(first['total']):
                    page=client.get('/api/browse',params={**args,'limit':1,'offset':offset,'sort':sort}).json()
                    assert {p['id'] for p in page['map']['items']}==expected
                    seen.append(page['items'][0]['id'])
                assert set(seen)==expected and len(seen)==len(expected)
            export=client.get('/api/export',params=args).json()
            assert {p['properties']['id'] for p in export['features']}==expected
        searched=client.get('/api/browse',params={**base,'display':'top','q':'山'}).json()
        assert searched['total']==searched['map']['total']==1
        assert client.get('/api/browse',params={**base,'display':'wrong'}).status_code==422
        assert client.get('/api/export',params={**base,'display_zoom':99}).status_code==422


def test_trail_deferral_applies_to_every_viewer_level_and_export(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC]);store=app.state.store
    store.enqueue(SOURCE,[(16,54896,28092)]);job=store.claim()
    rows=[row(1,text='山'),row(2,x=160,kind='trail',details={'dash_count':10})]
    for p in rows:
        p.pop('id');p.pop('source');p['box']=json.loads(p['box']);p['details']=json.loads(p['details'])
    store.finish(job,rows,{},[])
    base=dict(bbox=','.join(map(str,bounds())),source=SOURCE,display_zoom=15)
    with TestClient(app) as client:
        for mode in ['all','top','reduced','adaptive']:
            args={**base,'display':mode,'include_trails':False}
            result=client.get('/api/browse',params=args).json()
            assert result['display']['available']==1 and result['total']==1
            assert all(p['kind']=='text' for p in result['items']+result['map']['items'])
            export=client.get('/api/export',params=args).json()
            assert all(f['properties']['kind']=='text' for f in export['features'])
        # Archived proposals remain available through explicit API requests.
        assert client.get('/api/browse',params={**base,'kind':'trail'}).json()['total']==1
    assert store.pois(bounds())['total']==2


def test_zoom_reveals_candidates_without_changing_scores():
    rows=[row(i,x=10+20*i,score=.9) for i in range(6)]
    wide,_=choose(rows,bounds(),15,'top');close,_=choose(rows,bounds(),17,'top')
    assert set(wide)<=set(close) and len(close)>len(wide)


@pytest.mark.parametrize('level',['top','reduced','adaptive'])
def test_noise_save_does_not_promote_nearby_suppressed_detections(tmp_path,level):
    app=create_app(tmp_path,worker_enabled=False,registry=[SPEC]);store=app.state.store
    store.enqueue(SOURCE,[(16,54896,28092)]);job=store.claim()
    rows=[row(i,x=20+i,score=.7+i/100) for i in range(10)]+[row(20,x=150,text='山')]
    for p in rows:
        p.pop('id');p.pop('source');p['box']=json.loads(p['box']);p['details']=json.loads(p['details'])
    store.finish(job,rows,{},[])
    base=dict(bbox=','.join(map(str,bounds())),source=SOURCE,display_zoom=15,display=level)
    with TestClient(app) as client:
        before=client.get('/api/browse',params=base).json()
        before_ids={p['id'] for p in before['items']}
        # One or two visible detections in the dense cell, excluding the sparse neighbor.
        removed=[p['id'] for p in before['items'] if p['text']=='溪'][:2]
        assert removed
        result=client.post(f'/api/pois/{removed[0]}/annotation',json=dict(
            classification='noise',member_ids=removed,sync_reading=True))
        assert result.status_code==200
        after=client.get('/api/browse',params=base).json()
        with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM pois').fetchone()[0]==11
        expected=before_ids-set(removed)
        assert {p['id'] for p in after['items']}==expected
        assert {p['id'] for p in after['map']['items']}==expected
        assert after['display']['available']==11-len(removed)
        assert after['display']['shown']==len(expected)
        assert after['display']['hidden']==11-len(removed)-len(expected)
        exported=client.get('/api/export',params=base).json()
        assert {p['properties']['id'] for p in exported['features']}==expected
        # All candidates still reveals the other proposals; no neighboring evidence is rejected.
        all_rows=client.get('/api/browse',params={**base,'display':'all'}).json()
        assert all_rows['total']==11-len(removed)
        hidden=client.get('/api/browse',params={**base,'display':'all','visibility':'hidden'}).json()
        assert {p['id'] for p in hidden['items']}==set(removed)
        for p in all_rows['items']:assert store.poi(p['id'])['annotations']==[]
        client.post(f'/api/pois/{removed[0]}/annotation',json=dict(
            classification='poi',member_ids=removed,sync_reading=True))
        restored=client.get('/api/browse',params=base).json()
        assert {p['id'] for p in restored['items']}==before_ids
