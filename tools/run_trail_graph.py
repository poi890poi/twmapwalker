import json,sys,time,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image
from mapwalker.detectors import CONFIG
from trail_graph_candidate import graph_trails,dash_graph,safe_trails
OUT=ROOT/'evidence/detection-round2'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--split',required=True);parser.add_argument('--safe',action='store_true');args=parser.parse_args()
 method='trails-safe' if args.safe else 'trails-graph';stem=method+'-'+args.split;target=OUT/(stem+'.jsonl')
 if target.exists():raise RuntimeError('Preserve runs')
 suite=json.loads((OUT/('holdout-inputs.json' if args.split=='holdout' else 'inputs.json')).read_text('utf-8'))
 for s in [s for s in suite['scenes'] if s['split']==args.split]:
  path=OUT/s['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256'];im=Image.open(path).convert('RGB');tick=time.perf_counter();ps=(safe_trails if args.safe else graph_trails)(im,CONFIG);ms=(time.perf_counter()-tick)*1000
  with target.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(scene=s['id'],proposals=ps,total_inference_ms=ms))+'\n')
  print(stem,s['id'],len(ps),round(ms),flush=True)
 files=[Path(__file__),ROOT/'tools/trail_graph_candidate.py'];meta=dict(status='complete',method=method,split=args.split,code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
 for p in files:(OUT/(stem+'-'+p.name)).write_bytes(p.read_bytes())
 (OUT/(stem+'-run.json')).write_text(json.dumps(meta,indent=2),'utf-8')
if __name__=='__main__':main()
