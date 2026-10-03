import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from mapwalker.vegetation import analyze
from mapwalker.vegetation_evidence import VegetationEvidence

ROOT = Path(__file__).resolve().parents[1]


def case(pid):
    path=ROOT/'evidence/noise-verifier/dataset.json'
    r=next(r for r in json.loads(path.read_text('utf-8')) if r['id']==pid)
    return Image.open(path.parent/r['crop']).convert('RGB'),r['crop_box']


def fixture(tmp_path):
    im,box=case(38819)
    tile=Image.new('RGB',(256,256),'white');tile.paste(im,(80,80))
    folder=tmp_path/'tiles/frozen/JM50K_1916/16/100';folder.mkdir(parents=True)
    path=folder/'100.png';tile.save(path)
    record=dict(source='JM50K_1916',z=16,x=100,y=100,file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return dict(kind='symbol',source='JM50K_1916',z=16,x=100,y=100,box=[v+80 for v in box],manifest=[record],spec={'snapshot':'frozen'}),path


class Reader:
    def __init__(self,readings=None):self.readings=readings or [];self.calls=[]
    def suggest(self,item,mode):self.calls.append((item,mode));return {'readings':self.readings}


def test_native_scale_translation_and_large_label_ownership():
    image,box=case(38819)
    assert analyze(image,box,16)['status']=='candidate'
    translated=Image.new('RGB',(110,110),'white');translated.paste(image,(3,5))
    moved=[box[0]+3,box[1]+5,box[2]+3,box[3]+5]
    assert analyze(translated,moved,16)['status']=='candidate'
    assert not analyze(image.resize((image.width*2,image.height*2)),[v*2 for v in box],16)['matches']
    assert analyze(image,box,15)['status']=='unsupported-scale'
    for pid in (95054,'control-9','control-8','control-7'):
        im,b=case(pid);assert not analyze(im,b,16)['matches']


def test_review_evidence_is_read_only_and_requires_successful_number_guard(tmp_path):
    item,path=fixture(tmp_path);reader=Reader();service=VegetationEvidence(tmp_path,reader)
    before=json.dumps(item,sort_keys=True);payload=path.read_bytes()
    result=service.inspect(item)
    assert result['status']=='candidate' and result['preview'].startswith('data:image/png;base64,')
    assert reader.calls[0][1]=='numbers'
    assert json.dumps(item,sort_keys=True)==before and path.read_bytes()==payload
    reader.readings=[dict(text='0988',score=.86,angle=0)]
    result=service.inspect(item)
    assert result['status']=='numeric-context' and not result['matches'] and 'preview' not in result
    def fail(*args):raise RuntimeError('reader busy')
    reader.suggest=fail
    with pytest.raises(RuntimeError,match='busy'):service.inspect(item)


def test_integrity_failure_and_unsupported_kind_cannot_produce_hint(tmp_path):
    item,path=fixture(tmp_path);reader=Reader();service=VegetationEvidence(tmp_path,reader)
    assert service.inspect({**item,'kind':'trail'})['status']=='unsupported-kind'
    assert service.inspect({**item,'z':15})['status']=='unsupported-scale'
    assert not reader.calls
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):service.inspect(item)
    assert not reader.calls


def test_api_checks_automatic_pixels_without_editing_annotations(tmp_path):
    from fastapi.testclient import TestClient
    from mapwalker.app import create_app
    spec=dict(fingerprint='vegetation-test',name='text',version='test',config={},snapshot='frozen')
    app=create_app(tmp_path,worker_enabled=False,registry=[spec]);store=app.state.store
    store.enqueue('JM50K_1924_new',[(16,54886,28100)]);job=store.claim()
    store.finish(job,[dict(kind='text',text='山',score=.9,lon=121.5,lat=24.8,box=[0,0,30,30],details={},disposition='candidate')],{},[])
    with TestClient(app) as client:
        with store.connect() as db:pid=db.execute('SELECT id FROM pois').fetchone()[0]
        client.post(f'/api/pois/{pid}/reading',json={'value':'manual answer','status':'confirmed'})
        before=client.get(f'/api/pois/{pid}').json();captured=[]
        def inspect(item):captured.append(item);return dict(status='candidate',matches=[{'box':[0,0,10,20]}])
        app.state.vegetation_evidence.inspect=inspect
        assert app.state.vegetation_evidence.reader is app.state.reading_suggestions
        assert client.get(f'/api/pois/{pid}/vegetation-evidence').json()['status']=='candidate'
        assert set(captured[0])=={'box','source','z','x','y','spec','manifest','kind'}
        assert client.get(f'/api/pois/{pid}').json()==before
        assert client.get('/api/pois/9999/vegetation-evidence').status_code==404
        def fail(_):raise RuntimeError('Another map reading is in progress')
        app.state.vegetation_evidence.inspect=fail
        response=client.get(f'/api/pois/{pid}/vegetation-evidence')
        assert response.status_code==503 and 'in progress' in response.json()['detail']
        assert client.get(f'/api/pois/{pid}').json()==before
