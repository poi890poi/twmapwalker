import json

from fastapi.testclient import TestClient

from mapwalker.app import create_app
from mapwalker.geo import pixel_lonlat
from mapwalker.nearby_annotations import bounds,gap_m


def test_box_gap_across_tiles_uses_edges_not_centers():
    a=dict(box=[240,30,290,60],x=54886,y=28100,z=16)
    b=dict(box=[5,40,15,50],x=54887,y=28100,z=16)
    assert gap_m(bounds(a),bounds(b))==0
    b['box']=[40,40,50,50]
    assert 10<gap_m(bounds(a),bounds(b))<15


def test_nearby_api_latest_names_groups_provenance_and_no_writes(tmp_path):
    spec=dict(fingerprint='nearby-test',name='text',version='test',config={},snapshot='test')
    app=create_app(tmp_path,worker_enabled=False,registry=[spec]);store=app.state.store
    def add(source,boxes):
        store.enqueue(source,[(16,54886,28100)]);job=store.claim()
        rows=[]
        for box in boxes:
            lon,lat=pixel_lonlat(16,54886,28100,(box[0]+box[2])/2,(box[1]+box[3])/2)
            rows.append(dict(kind='text',text='',score=.9,box=box,lon=lon,lat=lat,details={},disposition='candidate'))
        store.finish(job,rows,{},[])
        with store.connect() as db:return [r[0] for r in db.execute('SELECT id FROM pois WHERE job_id=? ORDER BY id',(job['id'],))]
    ids=add('JM50K_1924_new',[[0,0,20,20],[25,0,500,20],[40,0,50,20],[45,0,55,20],
                             [60,0,70,20],[80,0,90,20],[1000,0,1020,20],[10,0,20,20],[120,0,130,20]])
    target,wide,group_a,group_b,noise,hidden,far,own,blank=ids
    other=add('JM50K_1916',[[0,0,20,20]])[0]
    def annotate(pid,name,classification='poi',group=None,**extra):
        with store.connect() as db:db.execute('INSERT INTO annotations(poi_id,payload,created) VALUES(?,?,0)',
            (pid,json.dumps(dict(ground_truth=name,classification=classification,group_id=group,**extra))))
    annotate(target,'Current','poi','own');annotate(own,'Current member','poi','own')
    annotate(wide,'Long label');annotate(group_a,'Same group','poi','group');annotate(group_b,'Same group','poi','group')
    annotate(noise,'Rejected','noise');annotate(hidden,'Hidden');annotate(far,'Far away');annotate(blank,'???')
    annotate(other,'Other edition',osm_type='relation',osm_id=4321,osm_name='Modern counterpart')
    store.set_visibility(hidden,True,())
    with TestClient(app) as client:
        before=client.get(f'/api/pois/{target}').json()
        result=client.get(f'/api/pois/{target}/nearby-annotations').json()
        # Existing visibility policy makes confirmed POIs visible even when a
        # legacy hidden flag exists. Recommendations follow that same policy.
        assert [r['name'] for r in result['candidates']]==['Other edition','Long label','Same group','Hidden']
        assert result['candidates'][0]['source']=='JM50K_1916' and not result['candidates'][0]['same_map']
        linked=result['candidates'][0]
        assert (linked['classification'],linked['osm_type'],linked['osm_id'],linked['osm_name'])==('poi','relation',4321,'Modern counterpart')
        assert result['candidates'][1]['osm_id'] is None
        assert result['candidates'][1]['distance_m']<50 # Long box center is much farther away.
        assert client.get(f'/api/pois/{target}').json()==before
        annotate(wide,'Renamed')
        assert client.get(f'/api/pois/{target}/nearby-annotations').json()['candidates'][1]['name']=='Renamed'
        annotate(other,'Other edition')
        assert client.get(f'/api/pois/{target}/nearby-annotations').json()['candidates'][0]['osm_id'] is None
        annotate(other,'Renamed',osm_type='node',osm_id=9876)
        same_name=[r for r in client.get(f'/api/pois/{target}/nearby-annotations').json()['candidates'] if r['name']=='Renamed']
        assert {r['osm_id'] for r in same_name}=={None,9876}
        annotate(other,'Other edition')
        annotate(wide,'Renamed','other')
        assert 'Renamed' not in [r['name'] for r in client.get(f'/api/pois/{target}/nearby-annotations').json()['candidates']]
        annotate(hidden,'Hidden','other')
        assert 'Hidden' not in [r['name'] for r in client.get(f'/api/pois/{target}/nearby-annotations').json()['candidates']]
        # Widely separated selected members must not fill the empty space
        # between them with a fictional overlapping group rectangle.
        annotate(far,'Current distant member','poi','own');annotate(hidden,'Middle')
        with store.connect() as db:db.execute('UPDATE pois SET box=? WHERE id=?',(json.dumps([500,0,520,20]),hidden))
        assert 'Middle' not in [r['name'] for r in client.get(f'/api/pois/{target}/nearby-annotations').json()['candidates']]
        assert client.get('/api/pois/9999/nearby-annotations').status_code==404
