"""Single-variable evidence ranking replay, labels used only after inference."""
import copy
import json
import math
import re
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.run_detection_proposals import load,save,sha,OUT
from mapwalker.evidence_sources import LocalEvidence
from mapwalker.multi_evidence import analyze
from mapwalker.osm import cell,normalize,distance_m

def main():
    old=ROOT/'evidence/multi-evidence';reading=ROOT/'evidence/reading-improvements'
    rows=load(old/'inputs.json');labels=load(old/'evaluation-labels.json');cache={};sources=LocalEvidence(ROOT/'data')
    for s in load(old/'osm-snapshots.json'):
        p=ROOT/'data/osm'/s['raw_path'];assert sha(p)==s['digest'];cache[s['key']]=normalize(load(p))
    nums=load(reading/'evaluation.json')['number_outputs']
    kana={r['id']:[v for v in r['readings'] if v['score']>=.65 and len(v['text'])<=40 and re.search(r'[\u3041-\u3096\u30a1-\u30fa]',v['text'])] for r in load(reading/'japanese.json')['rows']}
    stage_names=['baseline','plus-numbers','plus-kana'];results={k:[] for k in stage_names};shifts=[]
    # The population matches the frozen reading experiment; no labels select inputs.
    eligible={s['id'] for s in load(reading/'inputs.json') if s['role']=='automatic-box'}
    for row in rows:
        key=str(row['id'])
        if key not in eligible:continue
        features=cache.get(cell(row['lon'],row['lat'])[0],[])
        nearby=sorted([f for f in features if distance_m(f['geometry'],row['lon'],row['lat'])<=1000],key=lambda f:(distance_m(f['geometry'],row['lon'],row['lat']),f['properties']['osm_type'],f['properties']['osm_id']))[:200]
        gaz,_=sources.nearby(row['lon'],row['lat']);pool=nearby+gaz
        inferred={}
        for stage in stage_names:
            p=copy.deepcopy(row)
            if isinstance(p.get('details'),str):p['details']=json.loads(p['details'])
            p['details']=p.get('details') or {}
            extra=nums.get(key,[]) if stage=='plus-numbers' else kana.get(key,[]) if stage=='plus-kana' else []
            p['details']['reading_candidates']=p['details'].get('reading_candidates',[])+extra
            start=time.perf_counter();r=analyze(p,pool,sources);ms=(time.perf_counter()-start)*1000
            inferred[stage]=dict(id=key,result=r,ms=ms,added=extra)
        # Only now inspect evaluation labels and saved links.
        label=labels.get(key,{})
        for stage,r in inferred.items():
            expected=(label.get('osm_type'),label.get('osm_id'))
            cs=[c for c in r['result']['candidates'] if c['feature']['properties'].get('provider','osm')=='osm']
            r.update(classification=label.get('classification'),has_saved_link=bool(label.get('osm_id')),
                rank=next((i+1 for i,c in enumerate(cs) if (c['feature']['properties'].get('osm_type'),c['feature']['properties'].get('osm_id'))==expected),None) if label.get('osm_id') else None)
            results[stage].append(r)
        if label.get('osm_id'):
            expected=(label['osm_type'],label['osm_id'])
            for metres in (250,500,1000):
                for direction,dx,dy in [('E',metres,0),('W',-metres,0),('N',0,metres),('S',0,-metres)]:
                    p={**row,'lon':row['lon']+dx/(111320*math.cos(math.radians(row['lat']))),'lat':row['lat']+dy/111320}
                    r=analyze(p,pool,sources);cs=[c for c in r['candidates'] if c['feature']['properties'].get('provider','osm')=='osm']
                    rank=next((i+1 for i,c in enumerate(cs) if (c['feature']['properties'].get('osm_type'),c['feature']['properties'].get('osm_id'))==expected),None)
                    shifts.append(dict(id=key,metres=metres,direction=direction,rank=rank,state=r['state']))
    summary={stage:dict(population=len(rs),linked=sum(r['has_saved_link'] for r in rs),top1=sum(r['has_saved_link'] and r['rank']==1 for r in rs),top3=sum(r['has_saved_link'] and r['rank'] is not None and r['rank']<=3 for r in rs),
        added_to=sum(bool(r['added']) for r in rs),noise_total=sum(r['classification']=='noise' for r in rs),noise_supported=sum(r['classification']=='noise' and r['result']['state']!='unknown' for r in rs)) for stage,rs in results.items()}
    # Lossless dictionary encoding avoids repeating full OSM geometry thousands
    # of times. The key identifies the exact feature bytes used by inference.
    features={}
    import hashlib
    for rs in results.values():
        for row in rs:
            for candidate in row['result']['candidates']:
                feature=candidate.pop('feature')
                identity=hashlib.sha256(json.dumps(feature,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                features[identity]=feature;candidate['feature_ref']=identity
    save(OUT/'evidence-ranking.json',dict(summary=summary,stages=results,features=features,shifts=shifts,
        shift_limit='Fixed original candidate pool, four artificial directions. Radius/ranking sensitivity only; no independently measured drift or new coverage.',
        provenance={str(p.relative_to(ROOT)):sha(p) for p in [old/'inputs.json',old/'evaluation-labels.json',old/'osm-snapshots.json',reading/'evaluation.json',reading/'japanese.json',ROOT/'mapwalker/multi_evidence.py',ROOT/'mapwalker/evidence_sources.py',ROOT/'data/multi-evidence/sources.json',Path(__file__)]}))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
