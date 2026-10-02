import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mapwalker.app import create_app
from mapwalker.reading_suggestions import ReadingSuggestions,evidence_crop,read_pixels,unrotate_box


def sample(tmp_path):
    records=[]
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            folder=tmp_path/'tiles/frozen/JM50K_1924_new/16'/str(100+dx);folder.mkdir(parents=True,exist_ok=True)
            path=folder/f'{100+dy}.png';Image.new('RGB',(256,256),(100+dx,100+dy,80)).save(path)
            records.append(dict(source='JM50K_1924_new',z=16,x=100+dx,y=100+dy,file=path.name,
                                sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return dict(box=[-10,20,40,60],spec={'snapshot':'frozen'},manifest=records,
                source='JM50K_1924_new',z=16,x=100,y=100,kind='text')


def test_context_crosses_tiles_and_fails_on_missing_or_changed_original(tmp_path):
    item=sample(tmp_path);image,box,_=evidence_crop(tmp_path,item,64)
    assert image.size==(178,168) and box==[64,64,114,104]
    assert image.getpixel((0,100))==(99,100,80)
    assert image.getpixel((100,100))==(100,100,80)
    path=tmp_path/'tiles/frozen/JM50K_1924_new/16/99/100.png';path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):evidence_crop(tmp_path,item,64)
    item['manifest']=[]
    with pytest.raises(ValueError,match='does not cover'):evidence_crop(tmp_path,item,64)


def test_recognition_crop_matches_the_frozen_truncation_contract(tmp_path):
    item=sample(tmp_path);item['box']=[10.5,20.5,40.5,60.5]
    baseline,_,_=evidence_crop(tmp_path,item,8,cover_box=False)
    expanded,_,_=evidence_crop(tmp_path,item,8)
    assert baseline.size==(46,56) and expanded.size==(47,57)
    assert expanded.crop((0,0,*baseline.size)).tobytes()==baseline.tobytes()


def test_readings_preserve_digits_and_ambiguity_but_exclude_nearby_unrelated_labels():
    image=Image.new('RGB',(200,160))
    def detector(_):return [dict(text='1059.',score=.92,box=[50,50,150,90]),
        dict(text='999',score=.99,box=[0,0,10,10]),dict(text='1O59',score=.99,box=[50,50,150,90])]
    result=read_pixels(image,[60,60,100,100],'numbers',detector)
    assert [r['text'] for r in result]==['1059.'] # No guessing O→0 or stripping decimal punctuation.
    assert unrotate_box([5,10,25,40],90,100,80)==[60,5,90,25]
    assert unrotate_box([5,10,25,40],270,100,80)==[10,55,40,75]
    def japanese(*args,**kwargs):return [('ウ',.8),('山',.99),('ラ',.2)],None
    assert [r['text'] for r in read_pixels(image,[0,0,200,160],'kana',japanese)]==['ウ']


def test_cache_never_skips_pixel_integrity_checks_and_lock_recovers(tmp_path):
    item=sample(tmp_path);reader=ReadingSuggestions(tmp_path)
    reader.engines['numbers']=(lambda _:[],{'test':'digest'})
    first=reader.suggest(item,'numbers');assert not first['cached']
    assert reader.suggest(item,'numbers')['cached']
    reader.lock.acquire()
    with pytest.raises(RuntimeError,match='in progress'):reader.suggest(item,'numbers')
    reader.lock.release()
    with pytest.raises(ValueError,match='not installed'):reader.suggest(item,'kana')
    assert not reader.lock.locked()
    (tmp_path/'tiles/frozen/JM50K_1924_new/16/99/100.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):reader.suggest(item,'numbers')
    assert not reader.lock.locked()


def test_api_strips_manual_information_and_keeps_stored_findings_unchanged(tmp_path):
    spec=dict(fingerprint='reading-test',name='text',version='test',config={},snapshot='frozen')
    app=create_app(tmp_path,worker_enabled=False,registry=[spec]);store=app.state.store
    store.enqueue('JM50K_1924_new',[(16,54886,28100)]);job=store.claim()
    store.finish(job,[dict(kind='text',text='山',score=.9,lon=121.5,lat=24.8,box=[0,0,30,30],details={},disposition='candidate')],{},[])
    with TestClient(app) as client:
        with store.connect() as db:pid=db.execute('SELECT id FROM pois').fetchone()[0]
        client.post(f'/api/pois/{pid}/reading',json={'value':'manual answer','status':'confirmed'})
        before=client.get(f'/api/pois/{pid}').json();captured=[]
        def suggest(item,mode):captured.append(item);return dict(readings=[dict(text='123',score=.9,angle=0)])
        app.state.reading_suggestions.suggest=suggest
        assert client.get(f'/api/pois/{pid}/reading-suggestions?mode=numbers').status_code==200
        assert set(captured[0])=={'box','source','z','x','y','spec','manifest','kind'}
        assert client.get(f'/api/pois/{pid}').json()==before
        assert client.get('/api/pois/9999/reading-suggestions?mode=kana').status_code==404
        assert client.get(f'/api/pois/{pid}/reading-suggestions?mode=invalid').status_code==422
