import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from mapwalker.coverage_worker import assess, CoverageWorker, POLICY
from mapwalker.worker import Worker
from mapwalker.db import Store
from mapwalker.geo import lonlat


def test_paper_grain_can_be_empty_but_tiny_and_faint_ink_are_preserved():
    rng=np.random.default_rng(42)
    paper=Image.fromarray(np.clip(210+rng.normal(0,1,(256,256)),0,255).astype('uint8')).convert('RGB')
    assert assess(paper)['blank']
    assert assess(Image.new('RGB',(256,256),'white'))['blank']
    assert not assess(Image.new('RGB',(256,256),'black'))['blank']
    tiny=paper.copy();ImageDraw.Draw(tiny).rectangle((126,126,128,128),fill='#444444')
    assert not assess(tiny)['blank']
    faint=paper.copy();ImageDraw.Draw(faint).line([(0,100),(50,100)],fill=(190,190,190),width=2)
    assert not assess(faint)['blank']
    glyph=Image.new('RGB',(256,256),(210,210,210))
    font=ImageFont.truetype('C:/Windows/Fonts/msmincho.ttc',32)
    ImageDraw.Draw(glyph).text((100,100),'ウ',font=font,fill=(190,190,190))
    assert not assess(glyph.rotate(45,fillcolor=(210,210,210)))['blank']


class FakeCache:
    def __init__(self,tmp_path,image):
        import hashlib
        self.root=tmp_path/'fixture';self.path=tmp_path/'tile.png';image.save(self.path)
        self.calls=[];self.digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
    def get(self,source,z,x,y):
        self.calls.append((source,z,x,y))
        return self.path,dict(source=source,z=z,x=x,y=y,sha256=self.digest),True
    def mosaic(self,*args):
        raise AssertionError('Blank source must not download halo or modern mosaics')


def setup(tmp_path,monkeypatch,image):
    specs=[dict(fingerprint=n,name=n,version='test',config={},snapshot='fixture') for n in ('text','symbols')]
    monkeypatch.setattr('mapwalker.worker.specs',lambda:specs)
    store=Store(tmp_path/'test.sqlite3');store.register(specs)
    store.enqueue('JM50K_1924_new',[(16,54896,28092)])
    cache=FakeCache(tmp_path,image)
    return store,cache,CoverageWorker(store,cache)


def test_blank_finishes_without_modern_download_or_model_and_caches_assessment(tmp_path,monkeypatch):
    store,cache,worker=setup(tmp_path,monkeypatch,Image.new('RGB',(256,256),'white'))
    assert worker.once() and worker.once()
    assert not worker.once()
    assert worker.ocr is None and worker.regions is None
    assert len(cache.calls)==2 and all(c[0]=='JM50K_1924_new' for c in cache.calls)
    with store.connect() as db:
        jobs=db.execute('SELECT state,telemetry FROM jobs ORDER BY id').fetchall()
        assert all(j['state']=='complete' for j in jobs)
        telemetry=[json.loads(j['telemetry']) for j in jobs]
        assert telemetry[0]['detect_ms']==0 and telemetry[0]['coverage']['policy']==POLICY
        assert telemetry[1]['coverage']['assessment_cached']
        assert db.execute('SELECT COUNT(*) FROM historical_coverage').fetchone()[0]==1
        assert db.execute('SELECT COUNT(*) FROM pois').fetchone()[0]==0
    w,n=lonlat(54896.1,28092.1,16);e,s=lonlat(54896.9,28092.9,16)
    coverage=store.coverage([w,s,e,n],'JM50K_1924_new')
    assert coverage['blank_tiles']==1 and coverage['blank_checks']==2 and coverage['state']=='complete'
    from mapwalker.progress import plan_message
    assert 'Blank historical map area ignored' in plan_message([coverage],0)


def test_content_uses_unchanged_detector_and_records_coverage(tmp_path,monkeypatch):
    im=Image.new('RGB',(256,256),'white');ImageDraw.Draw(im).line([(0,100),(200,100)],fill='black',width=2)
    store,cache,worker=setup(tmp_path,monkeypatch,im);calls=[]
    def original(self,job):
        calls.append(job['id']);return [{'fixture':'untouched'}],{'total_ms':7},[{'fixture':'original'}]
    monkeypatch.setattr(Worker,'process',original)
    pois,telemetry,manifest=worker.process(store.claim())
    assert calls and pois==[{'fixture':'untouched'}] and manifest==[{'fixture':'original'}]
    assert telemetry['coverage']['blank'] is False and telemetry['total_ms']>=7


def test_new_coverage_policy_requeues_only_prior_blank_exclusions(tmp_path,monkeypatch):
    store,cache,worker=setup(tmp_path,monkeypatch,Image.new('RGB',(256,256),'white'))
    store.finish(store.claim(),[],{'skipped_reason':'blank_historical_map','coverage':{'policy':'old'}},[])
    store.finish(store.claim(),[],{'total_ms':10},[])
    CoverageWorker(store,cache)
    with store.connect() as db:
        assert [r[0] for r in db.execute('SELECT state FROM jobs ORDER BY id')]==['pending','complete']
        assert db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]==2
