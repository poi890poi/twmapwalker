import sys,json,time,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image
from mapwalker.detectors import CONFIG
from detection_candidates import thick_symbols,thick_trails,selective_scale,compact_scale
OUT=ROOT/'evidence/detection-round2'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('method',choices=['symbols-thick','trails-thick','craft-selective','craft-compact']);parser.add_argument('--split',choices=['development','fresh','holdout'],required=True);args=parser.parse_args()
 stem=args.method+'-'+args.split;target=OUT/(stem+'.jsonl')
 if target.exists():raise RuntimeError('Preserve existing runs')
 input_manifest=OUT/('holdout-inputs.json' if args.split=='holdout' else 'inputs.json');suite=json.loads(input_manifest.read_text('utf-8'));scenes=[s for s in suite['scenes'] if s['split']==args.split]
 if args.method.startswith('craft'):
  base={r['scene']:r for r in map(json.loads,(OUT/('craft-base-'+args.split+'.jsonl')).read_text('utf-8').splitlines())}
  large={r['scene']:r for r in map(json.loads,(OUT/('craft-scale3-'+args.split+'.jsonl')).read_text('utf-8').splitlines())}
 for s in scenes:
  path=OUT/s['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256'];im=Image.open(path).convert('RGB');tick=time.perf_counter()
  if args.method.startswith('craft'):ps=(selective_scale if args.method=='craft-selective' else compact_scale)(base[s['id']],large[s['id']])
  else:ps=(thick_symbols if args.method=='symbols-thick' else thick_trails)(im,CONFIG)
  ms=(time.perf_counter()-tick)*1000
  if args.method.startswith('craft'):ms+=base[s['id']]['total_inference_ms']+large[s['id']]['total_inference_ms']
  row=dict(scene=s['id'],proposals=ps,total_inference_ms=ms)
  with target.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  print(stem,s['id'],len(ps),round(ms),flush=True)
 files=[Path(__file__),ROOT/'tools/detection_candidates.py',ROOT/'mapwalker/trails.py']
 meta=dict(status='complete',method=args.method,split=args.split,inputs_sha256=hashlib.sha256(input_manifest.read_bytes()).hexdigest(),code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 for p in files:(OUT/(stem+'-'+p.name)).write_bytes(p.read_bytes())
 (OUT/(stem+'-run.json')).write_text(json.dumps(meta,indent=2),'utf-8')
if __name__=='__main__':main()
