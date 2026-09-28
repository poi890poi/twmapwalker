"""Post-run evaluation. Partial manual references do not supply proposals."""
import json,hashlib,statistics,sys
from pathlib import Path
import numpy as np,cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from run_symbol_first import iou
from trail_graph_candidate import dash_graph
from mapwalker.detectors import CONFIG
OUT=ROOT/'evidence/detection-round2'
def keep(p):return not p.get('repeating') or p.get('details',{}).get('trail_context')
def main():
 inputs=json.loads((OUT/'inputs.json').read_text('utf-8'))['scenes']+json.loads((OUT/'holdout-inputs.json').read_text('utf-8'))['scenes'];scenes={(s['split'],s['id']):s for s in inputs}
 refs={'development':json.loads((ROOT/'evidence/symbol-first/references.json').read_text('utf-8')),'fresh':json.loads((OUT/'fresh-references.json').read_text('utf-8')),'holdout':json.loads((OUT/'holdout-references.json').read_text('utf-8'))};summary={};allrows={}
 for path in sorted(OUT.glob('*.jsonl')):
  method,split=path.stem.rsplit('-',1)
  if split not in refs:continue
  rows=[json.loads(l) for l in path.read_text('utf-8').splitlines()];allrows[path.stem]=rows;byid={r['scene']:r for r in rows}
  marks=[]
  for ref in refs[split].get('marks',[]):
   best=max((iou(ref['box'],p['box']) for p in byid.get(ref['scene'],{}).get('proposals',[]) if keep(p)),default=0)
   marks.append(dict(**ref,best_iou=best,matched=best>=.25))
  counts=[sum(keep(p) for p in r['proposals']) for r in rows];times=[r['total_inference_ms'] for r in rows]
  negatives=[]
  for ref in refs[split].get('negative_regions',[]):
   a,b,c,d=ref['box'];ps=byid.get(ref['scene'],{}).get('proposals',[])
   negatives.append(dict(**ref,count=sum(keep(p) and a<=(p['box'][0]+p['box'][2])/2<c and b<=(p['box'][1]+p['box'][3])/2<d for p in ps)))
  topology=dict(edges=0,unsupported_edges=0,length_px=0.,unsupported_length_px=0.);paths=[]
  if method.startswith('trails'):
   for row in rows:
    s=scenes[(split,row['scene'])];im=Image.open(OUT/s['path']).convert('RGB');dashes,graph=dash_graph(im,CONFIG);lookup={tuple(d['center']):i for i,d in enumerate(dashes)}
    if method in ['trails-base','trails-graph','trails-safe']:
     for p in row['proposals']:
      points=p['details']['pixel_path']
      for a,b in zip(points,points[1:]):
       i,j=lookup[tuple(a)],lookup[tuple(b)];length=float(np.linalg.norm(np.array(a)-b));topology['edges']+=1;topology['length_px']+=length
       if j not in graph[i]:topology['unsupported_edges']+=1;topology['unsupported_length_px']+=length
   for ref in refs[split].get('paths',[]):
    trace=np.zeros((384,384),'uint8');pred=trace.copy();cv2.polylines(trace,[np.round(ref['points']).astype('int32')],False,1,1)
    for p in byid[ref['scene']]['proposals']:cv2.polylines(pred,[np.round(p['details']['pixel_path']).astype('int32')],False,1,1)
    a,b,c,d=ref['roi'];roi=np.zeros_like(trace);roi[b:d,a:c]=1;kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(13,13));near_pred=cv2.dilate(pred,kernel);near_ref=cv2.dilate(trace,kernel)
    covered=int(((trace!=0)&(near_pred!=0)).sum());total=int(trace.sum());unsupported=int(((pred!=0)&(near_ref==0)&(roi!=0)).sum());predtotal=int((pred*roi).sum())
    paths.append(dict(scene=ref['scene'],coverage=covered/max(1,total),reference_pixels=total,covered_pixels=covered,predicted_pixels_in_roi=predtotal,unsupported_pixels_in_roi=unsupported))
  summary[path.stem]=dict(method=method,split=split,scenes=len(rows),mark_hits=sum(m['matched'] for m in marks),mark_total=len(marks),marks=marks,negative_regions=negatives,total_proposals=sum(counts),median_proposals=statistics.median(counts),median_ms=statistics.median(times),p95_ms=float(np.percentile(times,95)),max_ms=max(times),topology=topology,paths=paths)
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
 (OUT/'review-data.json').write_text(json.dumps(dict(scenes=inputs,references=refs,results=allrows),ensure_ascii=False),'utf-8')
 for key,s in summary.items():print(key,s['mark_hits'],s['mark_total'],'count',s['total_proposals'],'median',s['median_proposals'],'bad_edges',s['topology']['unsupported_edges'],'path',s['paths'])
if __name__=='__main__':main()
