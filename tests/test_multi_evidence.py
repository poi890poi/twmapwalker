import csv
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from mapwalker.app import create_app
from mapwalker.evidence_sources import LocalEvidence
from mapwalker.multi_evidence import analyze,elevation


def poi(text='山埔'):
    return dict(text=text,details={'reading_candidates':[{'text':text[::-1]}]},lon=121.5,lat=24.8)


def feature(oid=1,name='內茅埔山',lon=121.503,**tags):
    return dict(type='Feature',geometry=dict(type='Point',coordinates=[lon,24.8]),
                properties=dict(osm_type='node',osm_id=oid,name=name,tags={'name':name,**tags},
                                url=f'https://www.openstreetmap.org/node/{oid}'))


def test_raw_fragment_and_direction_outrank_proximity_without_manual_leakage():
    nearby=feature(2,'別山',121.50001,natural='peak')
    distant=feature(1,natural='peak')
    raw=poi()
    result=analyze(raw,[nearby,distant])
    assert result['state']=='name-supported'
    assert result['candidates'][0]['feature']==distant
    assert result['candidates'][0]['name_match']['reading']=='埔山'
    changed={**raw,'reading':'別山','annotation':{'osm_id':2,'classification':'noise'},'review':'rejected'}
    assert analyze(changed,[nearby,distant])==result


def test_generic_character_is_type_context_and_no_modern_match_is_unknown():
    result=analyze(poi('山'),[feature(2,'某村',121.50001,place='hamlet'),feature(1,natural='peak')])
    assert result['state']=='unknown'
    assert result['candidates'][0]['feature']['properties']['osm_id']==1
    assert all(c['name_match'] is None for c in result['candidates'])
    assert analyze(poi(),[])['state']=='unknown'
    assert analyze(poi('山川'),[feature(name='山川峰')])['state']=='unknown'


def test_historical_alias_and_fuzzy_name_do_not_require_exact_modern_spelling():
    result=analyze(poi('ルモン山'),[feature(name='露門山',old_name='ルモン山')])
    assert result['state']=='name-supported'
    assert result['candidates'][0]['name_match']['alias']=='ルモン山'
    assert analyze(poi('小茅埔'),[feature()])['state']=='unknown' # short fuzzy fragment is unsafe
    assert analyze(poi('内茅埔山'),[feature()])['state']=='name-supported'


def test_competing_peaks_and_duplicate_providers_are_not_independent_votes():
    first=feature();second=feature(2,'外茅埔山',121.507)
    assert analyze(poi(),[first,second])['state']=='ambiguous'
    duplicate=feature(lon=121.5031)
    duplicate['properties'].update(provider='moi',record_id=4)
    assert analyze(poi(),[first,duplicate])['state']=='name-supported'
    assert analyze(poi(),[first,first])['total']==1


def test_height_agreement_cannot_confirm_peak_or_contour_even_with_terrain():
    class Terrain:
        def point(self,*args):return dict(state='available',elevation_m=1460,native_resolution_m=20,peak_like=True)
    result=analyze(poi('1461'),[feature(natural='peak',ele='1461.9')],Terrain())
    assert result['state']=='elevation-compatible'
    assert result['numeric_note'] and result['candidates'][0]['name_match'] is None
    assert result['candidates'][0]['evidence'][-1]['modern_height_compatible']
    for value in ['NaN','inf','1,234,5','1400 ft','99999','-100']:
        assert elevation(value) is None
    assert elevation('１４１７,２')==1417.2
    # A geometry outside the displacement search area cannot supply support.
    assert analyze(poi('1461'),[feature(lon=121.53,ele='1461')],Terrain())['state']=='unknown'


def install(tmp_path,key,path):
    root=tmp_path/'multi-evidence';root.mkdir(exist_ok=True)
    target=root/path.name;target.write_bytes(path.read_bytes())
    manifest=root/'sources.json'
    entries=json.loads(manifest.read_text()) if manifest.exists() else {}
    entries[key]=dict(file=path.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(entries))


def test_gazetteer_nearby_aliases_and_tamper_fail_closed(tmp_path):
    path=tmp_path/'places.csv'
    fields=['Type','PlaceName','AnotherName','Longitude','Latitude','DataSource']
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerow(dict(Type='自然地理實體',PlaceName='露門山',AnotherName='ルモン山;另一名',
                             Longitude='121.503',Latitude='24.8',DataSource='地名辭書'))
    install(tmp_path,'gazetteer',path)
    source=LocalEvidence(tmp_path)
    features,coverage=source.nearby(121.5,24.8)
    assert coverage['state']=='available' and len(features)==1
    assert analyze(poi('ルモン山'),features)['state']=='name-supported'
    assert source.nearby(121.8,24.8)[0]==[]
    (tmp_path/'multi-evidence/places.csv').write_text('changed')
    assert source.nearby(121.5,24.8)[1]['state']=='unavailable'
    assert LocalEvidence(tmp_path).nearby(121.5,24.8)[1]['state']=='unavailable'


def test_native_terrain_crs_grid_nodata_and_missing_dependency_fallback(tmp_path,monkeypatch):
    rasterio=pytest.importorskip('rasterio')
    import numpy as np
    from rasterio.transform import from_origin
    from rasterio.warp import transform
    x,y=transform('EPSG:4326','EPSG:3826',[121.5],[24.8])
    values=np.full((31,31),900,dtype='float32');values[15,15]=1000
    path=tmp_path/'terrain.tif'
    with rasterio.open(path,'w',driver='GTiff',width=31,height=31,count=1,dtype='float32',
                       crs='EPSG:3826',transform=from_origin(x[0]-310,y[0]+310,20,20),nodata=-9999) as out:
        out.write(values,1)
    install(tmp_path,'terrain',path)
    source=LocalEvidence(tmp_path);result=source.point(121.5,24.8)
    assert result['elevation_m']==1000 and result['native_resolution_m']==20
    assert result['peak_like'] and result['valid_fraction']==1
    assert source.point(120,23)['state']=='outside-coverage'
    assert LocalEvidence(tmp_path/'missing').point(121.5,24.8)['state']=='unavailable'
    values[15,15]=-9999
    with rasterio.open(path,'r+') as out:out.write(values,1)
    install(tmp_path,'terrain',path)
    source=LocalEvidence(tmp_path)
    assert source.point(121.5,24.8)['state']=='nodata'
    assert source.terrain_status()['native_resolution_m']==20
    result=analyze(poi(),[feature(lon=121.5)],source)
    assert result['candidates'][0]['evidence'][-1]['state']=='nodata'
    import sys
    monkeypatch.setitem(sys.modules,'rasterio',None)
    assert LocalEvidence(tmp_path).terrain_status()['state']=='unavailable'


def test_inspector_api_missing_sources_and_annotations_preserve_detection_selection(tmp_path):
    spec=dict(fingerprint='test',name='text',version='test',config={},snapshot='test')
    app=create_app(tmp_path,worker_enabled=False,registry=[spec]);store=app.state.store
    store.enqueue('JM50K_1924_new',[(16,54886,28100)]);job=store.claim()
    row={**poi(), 'kind':'text','score':.95,'box':[0,0,30,30],'disposition':'candidate'}
    store.finish(job,[row],{},[])
    with TestClient(app) as client:
        params=dict(bbox='121.49,24.79,121.51,24.81',display='top')
        before=client.get('/api/browse',params=params).json()
        pid=before['items'][0]['id']
        first=client.get(f'/api/pois/{pid}/supporting-evidence').json()
        assert first['state']=='unknown' and first['coverage']['gazetteer']['state']=='unavailable'
        raw=json.dumps({'elements':[{'type':'node','id':1,'lon':121.503,'lat':24.8,
                                    'tags':{'name':'內茅埔山','natural':'peak'}}]}).encode()
        app.state.osm.once(lambda _:raw)
        result=client.get(f'/api/pois/{pid}/supporting-evidence').json()
        assert result['state']=='name-supported'
        assert client.get('/api/browse',params=params).json()==before
        client.post(f'/api/pois/{pid}/reading',json={'value':'completely different','status':'confirmed'})
        assert client.get(f'/api/pois/{pid}/supporting-evidence').json()==result
        assert client.get('/api/pois/9999/supporting-evidence').status_code==404
