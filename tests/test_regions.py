import json
import subprocess
from pathlib import Path
import pytest
from PIL import Image
from mapwalker.detectors import CONFIG
from mapwalker.region_model import compact_additions
from mapwalker.regions import RegionDetector


def test_new_scale_recovers_unread_region_without_replacing_existing_glyph():
    def region(box,score):return dict(kind='text',text='',score=score,box=box)
    original=region([80,290,140,345],.5)
    added=region([85,96,131,135],.57)
    giant=region([50,250,200,380],.95)
    weak=region([200,10,230,40],.32)
    duplicate=region([82,288,145,347],.9)
    output=compact_additions([original],[added,giant,weak,duplicate])
    assert output==[original,added]
    assert all(p['text']=='' for p in output)  # No supplied reading or invented character count.


def test_isolated_inference_failure_is_not_a_successful_empty_detection(monkeypatch):
    import hashlib,sys
    python=Path(sys.executable)
    spec=dict(runtime=dict(python=str(python),python_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),weights='test-local-weights'),models={'weights':'abc'},packages={})
    detector=RegionDetector(spec)
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],90)
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(subprocess.TimeoutExpired):detector(Image.new('RGB',(384,384)),CONFIG)
    assert detector.last_timing=={}


def test_region_result_retains_unread_text_and_backend_timing(monkeypatch):
    import hashlib,sys
    python=Path(sys.executable)
    spec=dict(runtime=dict(python=str(python),python_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),weights='test-local-weights'),models={'weights':'abc'},packages={})
    proposal=dict(kind='text',text='',score=.6,box=[90,90,120,120],details={'recognition':'not attempted'})
    def complete(*args,**kwargs):
        assert kwargs['timeout']==90 and not kwargs.get('shell')
        assert kwargs['input']
        return subprocess.CompletedProcess(args[0],0,json.dumps({'proposals':[proposal],'timing':{'detect_ms':12}}).encode(),b'')
    monkeypatch.setattr(subprocess,'run',complete)
    detector=RegionDetector(spec)
    assert detector(Image.new('RGB',(384,384)),CONFIG)==[proposal]
    assert detector.last_timing['detect_ms']==12
