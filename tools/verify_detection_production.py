"""Compare landed implementations with frozen experiment outputs on all 23 scenes."""
import sys,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from mapwalker.region_model import RegionModel
from mapwalker.trails import trail_proposals
from mapwalker.detectors import CONFIG
OUT=ROOT/'evidence/detection-round2'
def main():
 weights=ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth';model=RegionModel(weights);results=[]
 for file in ['inputs.json','holdout-inputs.json']:
  for s in json.loads((OUT/file).read_text('utf-8'))['scenes']:
   split=s['split'];image=Image.open(OUT/s['path']).convert('RGB')
   expected_text=next(r for r in map(json.loads,(OUT/('craft-compact-'+split+'.jsonl')).read_text('utf-8').splitlines()) if r['scene']==s['id'])['proposals']
   expected_trails=next(r for r in map(json.loads,(OUT/('trails-safe-'+split+'.jsonl')).read_text('utf-8').splitlines()) if r['scene']==s['id'])['proposals']
   tick=time.perf_counter();text=model(image);elapsed=(time.perf_counter()-tick)*1000;trails=trail_proposals(image,CONFIG)
   assert len(text)==len(expected_text),(s['id'],'text count')
   for a,b in zip(text,expected_text):assert np.allclose(a['box'],b['box'],atol=1e-4) and abs(a['score']-b['score'])<1e-4,(s['id'],'text box or score')
   assert len(trails)==len(expected_trails),(s['id'],'trail count')
   for a,b in zip(trails,expected_trails):assert a['box']==b['box'] and a['details']['pixel_path']==b['details']['pixel_path'],(s['id'],'trail geometry')
   results.append(dict(scene=s['id'],split=split,text_regions=len(text),trails=len(trails),text_ms=elapsed,parity=True))
   print(split,s['id'],'PASS',len(text),len(trails),round(elapsed),flush=True)
 (OUT/'production-parity.json').write_text(json.dumps(dict(results=results,weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),code={name:hashlib.sha256((ROOT/'mapwalker'/name).read_bytes()).hexdigest() for name in ['region_model.py','trails.py','trail_paths.py']}),indent=2),'utf-8')
if __name__=='__main__':main()
