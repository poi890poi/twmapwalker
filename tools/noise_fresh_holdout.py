"""Post-lock spatial holdout for surviving HOG-mark and CRAFT-mark verifiers."""
import argparse
import hashlib
import json
import sqlite3
import sys
import time

import numpy as np
import noise_verifier_trial as t

BASE=t.OUT
OUT=BASE/'fresh'


def freeze():
    assert (BASE/'locked-model.json').exists() and (BASE/'craft/locked-model.json').exists()
    if (OUT/'dataset.json').exists(): raise RuntimeError('Preserve frozen holdout')
    OUT.mkdir(exist_ok=True); (OUT/'crops').mkdir(exist_ok=True)
    old=t.read(BASE/'dataset.json')
    scenes=t.read(t.ROOT/'evidence/symbol-first/inputs.json')['scenes']
    old=[r for r in old if 'source' in r]+scenes
    db=sqlite3.connect('file:'+str(t.ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    candidates=[]
    for row in db.execute('''SELECT p.id,p.box,p.kind,p.score,p.text,t.source,t.z,t.x,t.y
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm
        WHERE a.active=1 AND j.state='complete' AND p.kind IN ('text','symbol')'''):
        r=dict(row); r['box']=json.loads(r['box']); text=r.pop('text')
        w=r['box'][2]-r['box'][0]; h=r['box'][3]-r['box'][1]
        if not (2<=min(w,h) and max(w,h)<=160): continue
        if any(t.near(r,a,2) for a in old): continue
        r['stratum']='text-read' if r['kind']=='text' and text.strip() else r['kind']
        r['block']=f"{r['source']}:{r['z']}:{r['x']//4}:{r['y']//4}"
        r['order']=hashlib.sha256(f"noise-verifier-fresh-31003:{r['id']}".encode()).hexdigest()
        candidates.append(r)
    db.close()
    rows=[]; counts={}; used=set(); exclusions=[]
    # Eight per source and candidate family, at most one per 4x4 block globally.
    for r in sorted(candidates,key=lambda r:r['order']):
        key=r['source']+':'+r['stratum']
        if counts.get(key,0)>=8 or r['block'] in used: continue
        try: im,box,sources=t.crop_cached(r)
        except FileNotFoundError:
            exclusions.append(r['id']); continue
        r.pop('order'); r.update(label='unreviewed',classification='unreviewed',split='fresh-spatial',physical_group=str(r['id']),crop=f"crops/{r['id']}.png",crop_box=box,sources=sources)
        path=OUT/r['crop']; im.save(path); r['sha256']=t.digest(path)
        rows.append(r); used.add(r['block']); counts[key]=counts.get(key,0)+1
    if not rows: raise RuntimeError('No eligible rows; inspect actual job state names')
    t.OUT=OUT; t.write('dataset.json',rows)
    t.write('selection.json',dict(counts=counts,eligible=len(candidates),missing_context_exclusions=exclusions,rule='SHA256 fixed salt; 8 per source/kind/read-status; one per 4x4 block; exclude two-tile neighborhoods of frozen annotation areas and known protected controls; native cached pixels only',limitations='Stratified detected-candidate sample, not whole-map recall or prevalence. Prior unrelated research exposure not exhaustively excluded.',locks={str(p.relative_to(BASE)):t.digest(p) for p in [BASE/'locked-model.json',BASE/'craft/locked-model.json']}))
    t.sheets(rows,'input'); print(json.dumps(counts),flush=True)


def infer():
    rows=t.read(OUT/'dataset.json'); output={}
    for method,folder,feature_file in [('hog-mark',BASE,'features.npz'),('craft-mark',BASE/'craft','craft-features.npz')]:
        lock=t.read(folder/'locked-model.json'); train=np.load(folder/'features.npz')[method]
        fresh=np.load(OUT/feature_file)[method]; ids=np.array(lock['fit_indices'])
        model=t.train(train[ids],np.array(lock['fit_labels']))
        output[method]=[]
        for i,r in enumerate(rows):
            start=time.perf_counter(); score,ratio=t.predict(model,fresh[i:i+1]); elapsed=(time.perf_counter()-start)*1000
            score=float(score[0]); ratio=float(ratio[0]); reject=score>lock['thresholds'][method]
            output[method].append(dict(id=r['id'],score=score,ratio=ratio,reject=reject,guarded_reject=reject and ratio<t.PARAMS['guard_ratio'],inference_ms=elapsed))
    t.OUT=OUT; t.write('predictions.json',output)
    print('Fresh predictions saved. Labels are scored separately.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['freeze','infer'])
    globals()[parser.parse_args().stage]()
