"""Validate evidence integrity and independent evaluation/report relationships."""
import json,hashlib,sys
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/symbol-first'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 suite=json.loads((OUT/'inputs.json').read_text('utf-8'));checks=[]
 for s in suite['scenes']:assert sha(OUT/s['path'])==s['sha256'],s['id']
 checks.append('All 15 frozen scene hashes match.')
 passes=0
 for m in ['baseline-symbols','ppocr-det','craft-char','stable-ink']:
  run=json.loads((OUT/(m+'-run.json')).read_text('utf-8'));rows=[json.loads(l) for l in (OUT/(m+'.jsonl')).read_text('utf-8').splitlines()]
  assert run['status']=='complete' and run['rows']==len(rows)==15,m
  assert run['inputs_sha256']==sha(OUT/'inputs.json'),m
  raw=(OUT/(m+'-harness.py')).read_bytes();lf=raw.replace(b'\r\n',b'\n')
  assert run['harness_sha256'] in [hashlib.sha256(v).hexdigest() for v in [raw,lf,lf.replace(b'\n',b'\r\n')]],m
  assert 'references.json' not in raw.decode('utf-8'),m
  expected=suite['angles'] if m in ['ppocr-det','craft-char'] else [0]
  assert {r['scene'] for r in rows}=={s['id'] for s in suite['scenes']},m
  for row in rows:
   assert [p['angle'] for p in row['passes']]==expected
   assert all(p['ms']>=0 for p in row['passes'])
   passes+=len(row['passes'])
  checks.append(m+': complete; scenes, angles, input and frozen harness identity verified; no evaluation-reference file in runtime script.')
 old=json.loads((ROOT/'evidence/model-trials/ppocr6-run.json').read_text('utf-8'))
 new=json.loads((OUT/'ppocr-det-run.json').read_text('utf-8'))
 assert old['config']==new['config'],'PP-OCR initialization changed unexpectedly'
 checks.append('PP-OCR initialization config exactly matches prior run; inference call changes use_rec=False.')
 weights=json.loads((ROOT/'evidence/model-trials/weights.json').read_text('utf-8'))
 checked=[]
 for w in weights:
  if Path(w['path']).name in ['craft_mlt_25k.pth','PP-OCRv6_det_small.onnx']:
   assert sha(Path(w['path']))==w['sha256'];checked.append(Path(w['path']).name)
 assert len(checked)==2
 checks.append('CRAFT and PP-OCR detector checkpoint hashes match previous experiment.')
 class Links(HTMLParser):
  def __init__(self):super().__init__();self.links=[]
  def handle_starttag(self,tag,attrs):
   for k,v in attrs:
    if k in ['href','src'] and not v.startswith('#'):self.links.append(v)
 links=Links();links.feed((OUT/'report.html').read_text('utf-8'))
 for link in links.links:assert (OUT/link).is_file(),link
 checks.append(f'All {len(links.links)} static report links exist.')
 result=dict(checks=checks,completed_scene_runs=60,timed_passes=passes,production_scope='Trial tools/evidence only; production status assessed by git diff review')
 (OUT/'verification.json').write_text(json.dumps(result,indent=2),'utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
