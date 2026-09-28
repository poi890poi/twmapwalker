"""Versioned bridge to an explicitly configured, isolated GPU model runtime."""
import base64
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path
from .paths import ROOT

PACKAGES=('torch','easyocr','numpy','opencv-python','Pillow')

def region_spec(shared_config, shared_code, snapshot):
    local=ROOT/'.mapwalker-local.json'
    settings=json.loads(local.read_text('utf-8')) if local.exists() else {}
    runtime=settings.get('text_regions')
    if not runtime or not runtime.get('enabled'):
        return None
    python=Path(runtime['python']).resolve();weights=Path(runtime['weights']).resolve()
    if not python.is_file() or not weights.is_file():
        raise RuntimeError('Configured text-region runtime or weights are missing')
    packages=runtime['packages']
    if set(packages)!=set(PACKAGES):
        raise RuntimeError('Incomplete text-region package identity')
    folder=Path(__file__).parent
    code={**shared_code,**{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/'regions.py',folder/'region_model.py']}}
    spec=dict(name='text-regions',version='0.2.0-experimental',config=shared_config,code=code,snapshot=snapshot,
              region_policy=dict(scales=[2,3],angles=[0,-45,45,90,180,270],core=.2,peak=.3,min_core_area=5,context=6,canvas=1536,addition_peak=.5,addition_max_side=96),
              runtime=dict(python=str(python),python_sha256=hashlib.sha256(python.read_bytes()).hexdigest(),weights=str(weights)),packages=packages,
              models={weights.name:hashlib.sha256(weights.read_bytes()).hexdigest()})
    spec['fingerprint']=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
    return spec

class RegionDetector:
    def __init__(self,spec):
        self.spec=spec
        self.last_timing={}

    def __call__(self,image,config):
        spec=self.spec;runtime=spec['runtime'];python=Path(runtime['python'])
        if hashlib.sha256(python.read_bytes()).hexdigest()!=runtime['python_sha256']:
            raise RuntimeError('Text-region Python changed; re-register before running')
        payload=io.BytesIO();image.save(payload,format='PNG')
        command=[str(python),'-m','mapwalker.region_model','--weights',runtime['weights'],'--sha256',next(iter(spec['models'].values())),'--packages',json.dumps(spec['packages'])]
        result=subprocess.run(command,input=base64.b64encode(payload.getvalue()),capture_output=True,timeout=90,cwd=ROOT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:
            raise RuntimeError('Text-region inference failed: '+result.stderr.decode('utf-8',errors='replace')[-1800:])
        output=json.loads(result.stdout)
        if not isinstance(output.get('proposals'),list):
            raise RuntimeError('Text-region runtime returned an invalid result')
        self.last_timing=output['timing']
        return output['proposals']
