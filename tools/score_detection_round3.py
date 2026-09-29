"""Post-run scoring only: inference and training never import this module."""
import json,sys,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.region_model import iou
OUT=ROOT/'evidence/detection-round3'

def evaluate(path,refs,cutoff):
    rows={r['scene']:r for r in map(json.loads,path.read_text('utf-8').splitlines())}
    pred={k:[p for p in r['proposals'] if p['score']>=cutoff] for k,r in rows.items()}
    marks=[]
    for ref in refs.get('marks',[]):
        if ref['scene'] not in rows:continue
        overlap=max((iou(ref['box'],p['box']) for p in pred[ref['scene']]),default=0)
        marks.append(dict(**ref,iou=overlap,matched=overlap>=.25))
    negatives=[]
    for ref in refs.get('negative_regions',[]):
        if ref['scene'] not in rows:continue
        a,b,c,d=ref['box']
        count=sum(a<=(p['box'][0]+p['box'][2])/2<c and b<=(p['box'][1]+p['box'][3])/2<d for p in pred[ref['scene']])
        negatives.append(dict(**ref,count=count))
    return dict(cutoff=cutoff,matched=sum(r['matched'] for r in marks),references=len(marks),marks=marks,negative_proposals=sum(r['count'] for r in negatives),negative_regions=negatives,proposals={k:len(v) for k,v in pred.items()},median_proposals=statistics.median(map(len,pred.values())),median_ms=statistics.median(r['total_inference_ms'] for r in rows.values()))

def main():
    dev=json.loads((ROOT/'evidence/symbol-first/references.json').read_text('utf-8'))
    fresh=json.loads((OUT/'fresh-references.json').read_text('utf-8'))
    final=json.loads((OUT/'final-references.json').read_text('utf-8'))
    runs={'original-dev':ROOT/'evidence/detection-round2/craft-compact-development.jsonl'}
    runs.update({p.stem:p for p in OUT.glob('*.jsonl')})
    result={}
    for name,path in runs.items():
        refs=final if 'final' in name else fresh if 'fresh' in name else dev
        # These are score-only experiment slices. report_detection_round3 uses
        # the actual display policy, including size and rotation support.
        result[name]=[evaluate(path,refs,t) for t in [.30,.56,.95]]
        print(name,[(r['cutoff'],f"{r['matched']}/{r['references']}",r['negative_proposals'],r['median_proposals']) for r in result[name]])
    (OUT/'scores.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':main()
