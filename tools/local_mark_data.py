"""Freeze a staged localized-learning experiment and a geographically fresh reserve."""
import hashlib
import json
import math
import sqlite3
from collections import Counter
from .contour_learner_data import ROOT,read,write,sha,near
from mapwalker.reading_suggestions import evidence_crop

OUT=ROOT/'evidence/local-mark-learning'
BASE=ROOT/'evidence/contour-learner'
PREV=ROOT/'evidence/noise-methods-survey'
CACHE=ROOT/'data/model-trials/local-mark-cache'
SEEDS=[7,19,43]


def main():
    OUT.mkdir(exist_ok=False);(OUT/'crops').mkdir();CACHE.mkdir(exist_ok=False)
    write(OUT/'contract.json',dict(type='Offline research; no production/DB mutation',
        objective='Preserve any meaningful or unknown mark inside mixed contour boxes; isolate pooling, weak hierarchy and parameter-efficient adaptation.',
        inputs='Pixels and target boxes for visual models. Labels train/evaluate only. Geography only for exclusion/splits. No Other-as-noise relabeling.',
        stage1=dict(methods=['mean','max','hierarchy'],encoder='Frozen DINOv2-small,392px view of196 native pixels; all target-overlapping tokens, no64-token truncation',
            head='384->64 GELU->3 logits: preserve,text,symbol; same head dimensions for all controls',
            pooling='mean logits versus maximum per-instance logit; hierarchy uses same max head plus known text/symbol positive bag losses, weight0.25',
            supervision='Contour bags negative; all others preserved. Fine labels only train their known positive branch, with contour bags negative for both. Unknowns have no fine-label loss.',
            optimizer='Full-batch AdamW lr0.003 weight_decay0.01,200epochs; fixed seeds7,19,43; no test-fold early stopping'),
        stage2=dict(selection='Best stage1 architecture by lowest old-challenge protected flags, then highest1924 contour hits, then total hits; reused challenge is development evidence only.',
            variants=['matched head-only continuation','rank4 LoRA on query/value in last encoder block plus same head'],
            training='Initialize both from same stage1 fold head.20epochs,AdamW lr0.001 weight_decay0.01,batch8,balanced loss,identical seeded minibatches. Frozen encoder prefix cached losslessly.',
            scope='One selected architecture only; paired continuation separates extra training from added trainable encoder parameters'),
        calibration='Three-seed mean noise probability; cutoff max protected spatial OOF score+.025, strict greater. Per-seed results also reported.',
        advancement='At least24/96 development contour hits, more than2/33 on1924,zero58 reused guard flags,zero protected flags on48 consumed prior holdout. Best qualifier by1924 then total hits advances alone.',
        fresh_acceptance='At least25% fresh visually labeled contours removed and zero protected/unknown flags. Fresh Kana/rare-symbol coverage remains necessary before automatic hiding.',
        multimodal='Only add a separately measured fusion stage after visual protection passes; missing external evidence must be neutral. No tuning on newly consumed holdout.',
        limitations='Small assistant-labeled sample, reused development data and failure set. Sparse fine labels. Model scores are not calibrated probabilities.',
        resource_budget='Small head plus last-block rank4 updates on existing GTX1650.20epoch adaptation cap; report training and cached scoring separately from full encoder extraction.',
        seeds=SEEDS))
    training=read(BASE/'training.json');guards=read(BASE/'guards.json');challenge=read(BASE/'holdout-inputs.json')
    labels=read(PREV/'holdout-labels.json');inverse={i:lab for lab,ids in labels.items() if isinstance(ids,list) for i in ids}
    challenge=[dict(r,label=inverse[r['index']],negative=inverse[r['index']]=='contour-fragment') for r in challenge]
    write(OUT/'training.json',training);write(OUT/'guards.json',guards);write(OUT/'challenge.json',challenge)
    # Exclude all prior contour/noise visual datasets, not only this fitting set.
    known=training+guards+challenge
    for path in [ROOT/'evidence/contour-samples/dataset.json',ROOT/'evidence/noise-verifier/dataset.json']:
        known+=read(path)
    ids={str(r['id']) for r in known};used=set();counts=Counter();fresh=[];errors=[]
    con=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
    pool=[]
    query="""SELECT p.id,p.kind,p.text,p.box,p.details,t.source,t.z,t.x,t.y,a.spec,j.manifest
    FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
    WHERE a.active=1 AND j.state='complete' AND p.disposition='candidate' AND t.z=16 AND p.kind IN ('text','symbol')"""
    for row in con.execute(query):
        r=dict(row);r['box']=json.loads(r['box']);a,b,c,d=r['box']
        if min(c-a,d-b)<3 or not 6<=max(c-a,d-b)<=160:continue
        txt=r['text'].strip();r['stratum']='symbol' if not txt else 'kana' if any('\u3040'<=v<='\u30ff' for v in txt) else 'numeric' if any(v.isdigit() for v in txt) else 'name'
        pool.append(r)
    con.close()
    for r in sorted(pool,key=lambda r:hashlib.sha256(f"local-mark-fresh-v1:{r['id']}".encode()).hexdigest()):
        cap=8 if r['stratum']=='kana' else 16
        if counts[r['stratum']]>=cap or str(r['id']) in ids or (r['x'],r['y']) in used or any(near(r,k) for k in known):continue
        for k in ('details','spec','manifest'):r[k]=json.loads(r[k])
        a,b,c,d=r['box'];left=math.floor((a+c)/2)-96;top=math.floor((b+d)/2)-96
        try:im,_,sources=evidence_crop(ROOT/'data',{**r,'box':[left,top,left+192,top+192]},0)
        except (OSError,ValueError) as exc:errors.append(dict(id=r['id'],error=str(exc)));continue
        path=OUT/'crops'/f"{r['id']}.png";im.save(path)
        fresh.append({k:r[k] for k in ('id','source','z','x','y','box','stratum')}|dict(index=len(fresh)+1,context=path.relative_to(ROOT).as_posix(),context_box=[a-left,b-top,c-left,d-top],context_sha256=sha(path),sources=sources))
        counts[r['stratum']]+=1;used.add((r['x'],r['y']))
    write(OUT/'fresh-inputs.json',fresh)
    write(OUT/'selection.json',dict(pool=len(pool),counts=dict(counts),fresh_count=len(fresh),excluded_prior_examples=len(known),errors=errors,
        rule='No prior IDs; >2 native-z16 tiles from all known contour/noise examples across editions; one target per geographic tile; predictions must be locked before sheets/labels'))
    write(OUT/'input-lock.json',dict(inputs={p.name:sha(p) for p in [OUT/'training.json',OUT/'guards.json',OUT/'challenge.json',OUT/'fresh-inputs.json',OUT/'contract.json']},folds_sha256=sha(BASE/'folds.json'),code_sha256=sha(ROOT/'tools/local_mark_data.py')))
    print('Fresh reserve frozen:',dict(counts),'No fresh pixels displayed.')


if __name__=='__main__':main()
