"""Record installed packages, exact weights and integrity checks for the trials."""
import hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/model-trials'
DATA=ROOT/'data/model-trials'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
 (OUT/'environment.txt').write_text(sys.version+'\n'+packages,'utf-8')
 baseline=Path(os.environ['TEMP'])/'mapwalker-runtime/Lib/site-packages/rapidocr_onnxruntime/models'
 weights=[]
 for root in [DATA/'models',baseline]:
  for p in sorted(root.rglob('*')):
   if p.suffix.lower() not in ['.pt','.pth','.onnx','.bin','.safetensors']:continue
   weights.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
 (OUT/'weights.json').write_text(json.dumps(weights,indent=2),'utf-8')
 library=DATA/'runtime/Lib/site-packages'
 (OUT/'rapidocr-model-registry.yaml').write_bytes((library/'rapidocr/default_models.yaml').read_bytes())
 suite=json.loads((OUT/'inputs.json').read_text('utf-8'));checks=[]
 for s in suite['discovery']+suite['recognition']:
  assert sha(OUT/s['path'])==s['sha256'],s['id']
 checks.append('All 23 frozen input SHA-256 hashes match.')
 expected={'baseline':138,'ppocr6':138,'craft':66,'manga':72,'dino':11,'yolo':11}
 for m,n in expected.items():
  run=json.loads((OUT/f'{m}-run.json').read_text('utf-8'))
  rows=[json.loads(l) for l in (OUT/f'{m}.jsonl').read_text('utf-8').splitlines()]
  assert run['status']=='complete' and run['rows']==len(rows)==n,m
  assert run['inputs_sha256']==sha(OUT/'inputs.json'),m
  # Snapshot text normalized CRLF to LF; original on-disk hash may use either.
  snapshot=(OUT/f'harness-{m}.py').read_bytes()
  candidates=[snapshot,snapshot.replace(b'\n',b'\r\n')]
  assert run['script_sha256'] in [hashlib.sha256(b).hexdigest() for b in candidates],m
  for r in rows:
   assert r['ms']>=0
  checks.append(f'{m}: complete, {n} calls, input and harness identity verified.')
 (OUT/'integrity.json').write_text(json.dumps(dict(checks=checks,weights=len(weights)),indent=2),'utf-8')
 print('\n'.join(checks))
if __name__=='__main__':main()
