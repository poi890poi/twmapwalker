"""Replay frozen automatic inputs, then score against separately saved links."""
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.evidence_sources import LocalEvidence
from mapwalker.multi_evidence import analyze
from mapwalker.osm import cell,normalize,distance_m

OUT=ROOT/'evidence/multi-evidence'


def main():
    rows=json.loads((OUT/'inputs.json').read_text('utf-8'))
    labels=json.loads((OUT/'evaluation-labels.json').read_text('utf-8'))
    snapshots=json.loads((OUT/'osm-snapshots.json').read_text('utf-8'))
    sources=LocalEvidence(ROOT/'data');cache={}
    for s in snapshots:
        raw=(ROOT/'data/osm'/s['raw_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==s['digest']
        cache[s['key']]=(s,normalize(json.loads(raw)))
    samples=[];counts=Counter();links=[];durations=[]
    stages={name:dict(states=Counter(),links=[]) for name in ('osm-readings','plus-gazetteer','plus-terrain')}
    for row in rows:
        key,_,_=cell(row['lon'],row['lat'])
        snapshot,features=cache.get(key,(None,[]))
        nearby=sorted([f for f in features if distance_m(f['geometry'],row['lon'],row['lat'])<=1000],
                      key=lambda f:(distance_m(f['geometry'],row['lon'],row['lat']),f['properties']['osm_type'],f['properties']['osm_id']))[:200]
        gaz,coverage=sources.nearby(row['lon'],row['lat'])
        start=time.perf_counter()
        result=analyze(row,nearby+gaz,sources)
        durations.append((time.perf_counter()-start)*1000)
        counts[result['state']]+=1
        label=labels.get(str(row['id']))
        variants={'osm-readings':analyze(row,nearby), 'plus-gazetteer':analyze(row,nearby+gaz), 'plus-terrain':result}
        for name,variant in variants.items():
            stages[name]['states'][variant['state']]+=1
            if label and label.get('osm_id'):
                candidates=[c['feature']['properties'] for c in variant['candidates'] if c['feature']['properties'].get('provider','osm')=='osm']
                rank=next((i+1 for i,p in enumerate(candidates) if (p.get('osm_type'),p.get('osm_id'))==(label['osm_type'],label['osm_id'])),None)
                stages[name]['links'].append(dict(id=row['id'],rank=rank))
        if result['state']!='unknown' or label:
            samples.append(dict(id=row['id'],source=row['source'],text=row['text'],result=result,
                                osm_sha256=snapshot['digest'] if snapshot else None))
        if label and label.get('osm_id'):
            expected=(label['osm_type'],label['osm_id'])
            def identity(f):p=f['properties'];return p.get('osm_type'),p.get('osm_id')
            candidate_osm=[c for c in result['candidates'] if c['feature']['properties'].get('provider','osm')=='osm']
            baseline=next((i+1 for i,f in enumerate(nearby) if identity(f)==expected),None)
            rank=next((i+1 for i,c in enumerate(candidate_osm) if identity(c['feature'])==expected),None)
            links.append(dict(id=row['id'],expected=expected,baseline_rank=baseline,rank=rank,
                              state=result['state'],osm_cached=snapshot is not None))
    annotated=Counter((labels[str(s['id'])]['classification'],s['result']['state']) for s in samples if str(s['id']) in labels)
    result=dict(counts=dict(counts),annotated={':'.join(k):v for k,v in annotated.items()},links=links,samples=samples,ablations=stages,
        timing=dict(count=len(durations),median_ms=statistics.median(durations),p95_ms=sorted(durations)[int(.95*len(durations))],max_ms=max(durations)),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'mapwalker/multi_evidence.py',ROOT/'mapwalker/evidence_sources.py']})
    (OUT/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
