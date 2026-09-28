import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from mapwalker.app import create_app
from mapwalker.db import Store
from mapwalker.detectors import CONFIG, TextDetector, developed_mask, filter_proposals, symbol_proposals
from mapwalker.geo import lonlat, pixel_lonlat, tile_range, validate_bbox, world
from mapwalker.sources import SOURCES, TileCache, tile_url
from mapwalker.junctions import junction_proposals
from mapwalker.trails import trail_proposals
from mapwalker.angled import angled_text_proposals, rotate_with_transform


def spec(fp='v1',name='symbols'):
    return dict(fingerprint=fp,name=name,version=fp,config=CONFIG,snapshot='test')


@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path/'test.sqlite')
    s.register([spec()])
    return s


def proposal(lon=121.55,lat=24.865):
    return dict(kind='symbol',text='',score=.35,lon=lon,lat=lat,box=[1,2,9,12],disposition='candidate')


def test_zero_result_success_is_recorded_and_not_requeued(store):
    assert store.enqueue('JM50K_1916',[(16,54895,28092)])==1
    job=store.claim()
    assert store.finish(job,[],{'candidates':0},[])
    assert store.enqueue('JM50K_1916',[(16,54895,28092)])==0
    assert store.claim() is None
    assert store.status()['counts']=={'complete':1}


def test_upgrade_backfills_all_tiles_and_hides_old_version_results(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    job=store.claim();store.finish(job,[proposal()],{},[])
    store.register([spec('v2')])
    assert store.pois((121,24,122,25))['total']==0
    new=store.claim()
    assert new['algorithm']=='v2'
    store.finish(new,[proposal()],{},[])
    assert store.pois((121,24,122,25))['total']==1
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM pois').fetchone()[0]==2
    store.register([spec('v2'),spec('new-text','text')])
    assert store.claim()['name']=='text'


def test_expired_lease_and_stale_worker_cannot_publish(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    old=store.claim(now=time.time()-1000)
    current=store.claim()
    assert old['id']==current['id'] and old['token']!=current['token']
    assert not store.finish(old,[proposal()],{},[])
    store.fail(old,'stale failure')
    assert store.finish(current,[proposal()],{},[])
    assert store.pois((121,24,122,25))['total']==1


def test_old_worker_cannot_run_a_new_algorithm_fingerprint(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    store.register([spec('v2')])
    assert store.claim(fingerprints=['v1']) is None
    assert store.claim(fingerprints=['v2'])['algorithm']=='v2'


def test_only_one_worker_claims_a_job(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda _:store.claim(),range(5)))
    assert sum(r is not None for r in results)==1


def test_failures_bounded_and_manual_retry_retains_attempt_history(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    for i in range(3):
        job=store.claim(now=time.time()+1000)
        store.fail(job,'network unavailable')
    assert store.status()['counts']=={'failed':1}
    assert store.retry_failed()==1
    assert store.claim()['attempts']==1
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]==4


def test_pause_survives_restart(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    store.pause(True)
    restarted=Store(store.path)
    assert restarted.claim() is None
    restarted.pause(False)
    assert restarted.claim() is not None


def test_results_publish_atomically(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    job=store.claim()
    with pytest.raises(KeyError):
        store.finish(job,[proposal(),{}],{},[])
    assert store.pois((121,24,122,25))['total']==0
    assert store.finish(job,[proposal()],{},[])


def test_bbox_pagination_and_reviews_are_separate(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    job=store.claim()
    store.finish(job,[proposal(),proposal(121.9)],{},[])
    result=store.pois((121.5,24.8,121.6,24.9),limit=1)
    assert result['total']==1
    p=result['items'][0]
    store.review(p['id'],'rejected','Contour fragment')
    assert store.poi(p['id'])['disposition']=='candidate'
    assert store.pois((121.5,24.8,121.6,24.9))['items'][0]['review']=='rejected'


def test_trail_crossing_viewport_is_returned_even_if_its_center_is_outside(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    job=store.claim()
    trail=dict(proposal(lon=121.70),kind='trail',details={'geometry':{'type':'LineString','coordinates':[[121.50,24.865],[121.90,24.865]]}})
    store.finish(job,[trail],{},[])
    result=store.pois((121.52,24.86,121.56,24.87))
    assert result['total']==1
    assert store.pois((121.10,24.86,121.20,24.87))['total']==0


def test_geo_roundtrip_and_pixel_owner_edges():
    x,y=world(121.55,24.865,16)
    assert lonlat(x,y,16)==pytest.approx((121.55,24.865))
    assert pixel_lonlat(16,54895,28092,256,0)==pixel_lonlat(16,54896,28092,0,0)
    with pytest.raises(ValueError):validate_bbox([float('nan'),24,122,25])
    with pytest.raises(ValueError):validate_bbox([121,25,120,24])


def test_source_native_zoom_and_xyz_order():
    assert SOURCES['JM50K_1916']['max_zoom']==SOURCES['JM50K_1924_new']['max_zoom']==16
    assert tile_url('EMAP',16,54895,28092).endswith('/16/28092/54895')
    assert 'JM50K_1924_new-png-16-54895-28092' in tile_url('JM50K_1924_new',16,54895,28092)
    with pytest.raises(ValueError):tile_url('JM50K_1916',17,1,1)


def test_known_repeating_fixture_removed_and_unique_mark_retained():
    image=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(image)
    for x in (80,115,150,185,220):
        draw.line([(x,110),(x+7,96),(x+14,110)],fill='black',width=2)
    draw.ellipse((120,210,140,230),outline='black',width=3)
    proposals=symbol_proposals(image)
    mask=np.zeros((384,384),bool)
    base=filter_proposals(proposals,mask,repetition=False,urban=False)
    candidate=filter_proposals(proposals,mask,repetition=True,urban=False)
    assert len(base)==6
    assert sum(p['disposition']=='excluded' for p in candidate)==5
    assert sum(p['disposition']=='candidate' for p in candidate)==1


def test_modern_mask_and_displacement_margin():
    image=Image.new('RGB',(384,384),(247,247,247));draw=ImageDraw.Draw(image)
    draw.rectangle((120,100,270,280),fill=(234,227,234))
    mask=developed_mask(image)
    assert mask[190,190] and not mask[50,50]
    p=dict(kind='symbol',text='',score=.35,box=[180,180,195,195])
    retained=filter_proposals([p],mask,urban=False)
    excluded=filter_proposals([p],mask,urban=True)
    assert retained[0]['disposition']=='candidate' and excluded[0]['reason']=='developed-area'
    # A finding on the estimated boundary stays reviewable under local displacement.
    ys,xs=np.nonzero(mask)
    edge=dict(p,box=[int(xs.min()),175,int(xs.min())+5,190])
    out=filter_proposals([edge],mask)[0]
    assert out['disposition']=='candidate' and out['details']['boundary_review']


def test_tile_halo_publishes_centers_once():
    ps=[dict(kind='text',text='文',score=.9,box=[45,90,75,110]),
        dict(kind='text',text='文',score=.9,box=[50,120,90,145]),
        dict(kind='text',text='文',score=.9,box=[310,180,340,205])]
    output=filter_proposals(ps,np.zeros((384,384),bool))
    assert len(output)==1 and output[0]['box'][0]==-14


def test_junctions_find_attached_mark_without_proposing_plain_line():
    plain=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(plain)
    draw.line((100,10,100,370),fill='black',width=4)
    assert junction_proposals(plain,CONFIG)==[]
    marked=plain.copy();draw=ImageDraw.Draw(marked)
    draw.line((80,150,120,150),fill='black',width=4)
    draw.line((80,158,120,158),fill='black',width=4)
    found=junction_proposals(marked,CONFIG)
    assert any(p['box'][0]<100<p['box'][2] and p['box'][1]<154<p['box'][3] for p in found)


def test_dashed_trail_preserved_while_repeated_vegetation_is_excluded():
    image=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(image)
    for y in range(95,250,24):
        draw.ellipse((105,y,109,y+10),fill='black')
    for x in (170,205,240,275):
        draw.line([(x,160),(x+7,146),(x+14,160)],fill='black',width=2)
    trails=trail_proposals(image,CONFIG)
    assert len(trails)==1 and trails[0]['details']['dash_count']==7
    candidates=filter_proposals(symbol_proposals(image),np.zeros((384,384),bool))
    dashes=[p for p in candidates if p['details'].get('trail_context')]
    assert dashes and all(p['disposition']=='candidate' for p in dashes)
    assert sum(p['reason']=='repeating-pattern' for p in candidates)==4


def test_rotated_text_coordinates_map_back_without_changing_location():
    image=Image.new('RGB',(384,384),'white')
    expected=np.array([[100,130],[130,130],[130,160],[100,160]],dtype=float)
    _,transform=rotate_with_transform(image,45)
    rotated=np.column_stack((expected,np.ones(4)))@transform.T
    def detector(image,config):
        return [dict(kind='text',text='test',score=.9,box=[0,0,1,1],details={'polygon':rotated.tolist()})]
    out=angled_text_proposals(image,{**CONFIG,'text_angles':[45]},detector)
    assert out[0]['box']==pytest.approx([100,130,130,160])
    assert out[0]['details']['angle_degrees_ccw']==45
    result=filter_proposals(out,np.zeros((384,384),bool))
    assert result[0]['box']==pytest.approx([36,66,66,96])


def test_rtl_reading_is_an_explicit_alternative_not_a_silent_rewrite():
    detector=TextDetector.__new__(TextDetector)
    detector.engine=lambda image:([[[[10,10],[110,10],[110,30],[10,30]],'溪後桶',.9]],[])
    result=detector(Image.new('RGB',(100,100),'white'))
    assert result[0]['text']=='溪後桶'
    assert result[0]['details']['reading_candidates']==[
        {'direction':'as-recognized','text':'溪後桶'},
        {'direction':'possible-right-to-left','text':'桶後溪'}]


def test_text_is_prioritized_over_high_score_non_text(store):
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    store.finish(store.claim(),[dict(proposal(),score=.99),dict(proposal(),kind='text',text='test label',score=.20)],{},[])
    assert store.pois((121,24,122,25))['items'][0]['kind']=='text'


def test_api_plan_bounds_filters_and_write_origin(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[spec()])
    with TestClient(app) as client:
        assert client.get('/').status_code==200
        assert client.post('/api/plan',json={'bbox':[121.549,24.864,121.550,24.865]}).status_code==200
        assert client.post('/api/plan',json={'bbox':[118,21.5,123,26]}).status_code==400
        assert client.get('/api/pois?bbox=nan,24,122,25').status_code==400
        assert client.get('/api/pois?bbox=121,24,122,25&limit=0').status_code==422
        assert client.post('/api/worker/pause',json={'paused':True},headers={'Origin':'https://elsewhere.test'}).status_code==403
        assert client.get('/api/pois/999').status_code==404
        assert client.get('/api/tiles/unknown/16/1/1').status_code==404


def test_view_coverage_does_not_equate_sample_completion_with_a_searched_view(tmp_path):
    app=create_app(tmp_path,worker_enabled=False,registry=[spec()])
    store=app.state.store
    store.enqueue('JM50K_1916',[(16,54895,28092)])
    store.finish(store.claim(),[],{},[])
    with TestClient(app) as client:
        r=client.get('/api/coverage-summary?source=JM50K_1916&bbox=121.54,24.85,121.57,24.88').json()
        assert r['complete']==1 and r['total']>1 and r['not_queued']==r['total']-1
        assert client.get('/api/coverage-summary?source=bad&bbox=121.54,24.85,121.57,24.88').status_code==400
