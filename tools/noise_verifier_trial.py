"""Offline, abstaining noise verification experiment. No production imports/writes.

Stages are deliberately separate: freeze, features, develop, evaluate, report.
Held-out labels never enter training or threshold selection.
"""
import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from probe_hollow_dots import crop_cached

OUT = ROOT / 'evidence/noise-verifier'
PARAMS = dict(seed=31003, ridge=.1, margin=.05, guard_ratio=.8,
              development='old 103 annotated findings; current labels frozen separately',
              features=['hog-mark', 'hog-context'],
              target='noise + visually identified vegetation-like or closed-contour Other',
              protect='poi + numeric + uncertain Other; all unseen Other initially unknown',
              decision='abstain unless score exceeds all protected spatial OOF scores + .05')


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def near(a, b, radius=1):
    return a['source'] == b['source'] and a['z'] == b['z'] and max(abs(a['x']-b['x']), abs(a['y']-b['y'])) <= radius


def physical_duplicate(a, b):
    if not near(a, b):
        return False
    aa = np.array(a['box']) + np.array([a['x'], a['y'], a['x'], a['y']])*256
    bb = np.array(b['box']) + np.array([b['x'], b['y'], b['x'], b['y']])*256
    area = np.prod(np.maximum(0, np.minimum(aa[2:], bb[2:])-np.maximum(aa[:2], bb[:2])))
    return area/max(1, min(np.prod(aa[2:]-aa[:2]), np.prod(bb[2:]-bb[:2]))) >= .6


def freeze():
    if (OUT/'dataset.json').exists():
        raise RuntimeError('Frozen inputs already exist')
    OUT.mkdir(exist_ok=True)
    (OUT/'crops').mkdir(exist_ok=True)
    original = read(ROOT/'evidence/hollow-dot/inputs.json')
    visual = read(ROOT/'evidence/hollow-dot/visual-labels.json')['labels']
    old_ids = {r['id'] for r in original}
    db = sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    current = []
    for row in db.execute('''SELECT p.id,p.box,p.kind,p.score,t.source,t.z,t.x,t.y,a.payload
        FROM annotations a JOIN pois p ON p.id=a.poi_id JOIN jobs j ON j.id=p.job_id
        JOIN tiles t ON t.id=j.tile_id
        WHERE a.id=(SELECT MAX(b.id) FROM annotations b WHERE b.poi_id=a.poi_id) ORDER BY p.id'''):
        r = dict(row); payload = json.loads(r.pop('payload')); r['box'] = json.loads(r['box'])
        r['classification'] = payload['classification']
        current.append(r)
    db.close()
    rows = []
    for r in original:
        label = visual.get(str(r['id']), r['annotation']['classification'])
        rows.append({k:r[k] for k in ('id','source','z','x','y','box','kind','score')} |
                    dict(label=label, split='development', classification=r['annotation']['classification']))
    for r in current:
        if r['id'] in old_ids:
            continue
        r['label'] = r['classification']
        r['split'] = 'new-nearby' if any(near(r,a) for a in rows if a['split']=='development') else 'new-spatial'
        rows.append(r)
    # Connected overlapping boxes are one physical group, never independent observations.
    parent = list(range(len(rows)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i,a in enumerate(rows):
        for j,b in enumerate(rows[:i]):
            if physical_duplicate(a,b): parent[root(i)] = root(j)
    for i,r in enumerate(rows):
        r['physical_group'] = str(rows[root(i)]['id'])
        r['block'] = f"{r['source']}:{r['z']}:{r['x']//4}:{r['y']//4}"
        im, box, sources = crop_cached(r)
        path = OUT/'crops'/f"{r['id']}.png"; im.save(path)
        r.update(crop=str(path.relative_to(OUT)), crop_box=box, sha256=digest(path), sources=sources)
    # These are protection controls, not fresh generalization references.
    scenes = {r['id']:r for r in read(ROOT/'evidence/symbol-first/inputs.json')['scenes']}
    for i,ref in enumerate(read(ROOT/'evidence/symbol-first/references.json')['marks']):
        scene = scenes[ref['scene']]; path = ROOT/'evidence/symbol-first'/scene['path']
        assert digest(path) == scene['sha256']
        box = ref['box']; side=max(96, math.ceil(max(box[2]-box[0],box[3]-box[1]))+32)
        x = round((box[0]+box[2]-side)/2); y = round((box[1]+box[3]-side)/2)
        im = Image.open(path).convert('RGB').crop((x,y,x+side,y+side))
        target = OUT/'crops'/f'control-{i}.png'; im.save(target)
        rows.append(dict(id=f'control-{i}', label='protected-symbol', classification='poi',
                         split='regression-control', name=ref['label'], physical_group=f'control-{i}',
                         crop=str(target.relative_to(OUT)), crop_box=[box[0]-x,box[1]-y,box[2]-x,box[3]-y],
                         sha256=digest(target), sources=[dict(path=str(path.relative_to(ROOT)),sha256=digest(path))]))
    write('parameters.json', PARAMS)
    write('dataset.json', rows)
    write('label-audit.json', dict(current=current, frozen_old_inputs_sha256=digest(ROOT/'evidence/hollow-dot/inputs.json'),
                                 visual_labels_sha256=digest(ROOT/'evidence/hollow-dot/visual-labels.json')))
    sheets(rows, 'input')
    print(json.dumps({s: {label:sum(r['split']==s and r['label']==label for r in rows) for label in sorted({r['label'] for r in rows})} for s in sorted({r['split'] for r in rows})}, indent=2))


def sheets(rows, prefix):
    for split in sorted({r['split'] for r in rows}):
        selected = [r for r in rows if r['split']==split]
        for start in range(0,len(selected),30):
            batch = selected[start:start+30]
            canvas = Image.new('RGB',(1000, math.ceil(len(batch)/5)*215),'white'); d=ImageDraw.Draw(canvas)
            for i,r in enumerate(batch):
                x=i%5*200; y=i//5*215
                im=Image.open(OUT/r['crop']).convert('RGB'); dd=ImageDraw.Draw(im)
                dd.rectangle(r['crop_box'],outline='red',width=1)
                im.thumbnail((190,170)); canvas.paste(im.resize((190,170)),(x,y+40))
                d.text((x+3,y+3),str(r['id'])+' '+r['label'],fill='black')
                d.text((x+3,y+20),r.get('result',''),fill='black')
            canvas.save(OUT/f'{prefix}-{split}-{start//30}.jpg')


HOG = cv2.HOGDescriptor((64,64),(16,16),(8,8),(8,8),9)


def hog(im):
    im=cv2.resize(im,(64,64),interpolation=cv2.INTER_AREA)
    v=HOG.compute(im).ravel()
    return v/max(1e-8,np.linalg.norm(v))


def features():
    rows=read(OUT/'dataset.json'); arrays={'hog-mark':[],'hog-context':[]}; timings=[]
    for r in rows:
        assert digest(OUT/r['crop'])==r['sha256']
        im=np.asarray(Image.open(OUT/r['crop']).convert('L'))
        t=time.perf_counter(); box=r['crop_box']
        a,b,c,d=[int(round(v)) for v in box]; pad=4
        mark=im[max(0,b-pad):min(len(im),d+pad),max(0,a-pad):min(im.shape[1],c+pad)]
        v=hog(mark); context=hog(im)
        arrays['hog-mark'].append(v)
        arrays['hog-context'].append(np.concatenate([v,context])/math.sqrt(2))
        timings.append((time.perf_counter()-t)*1000)
    np.savez_compressed(OUT/'features.npz',**{k:np.stack(v) for k,v in arrays.items()})
    write('feature-timing.json',dict(unit='ms / crop both representations',mean=statistics.mean(timings),median=statistics.median(timings),p95=float(np.percentile(timings,95)),maximum=max(timings),raw=timings,excludes='PNG decoding, disk I/O and model fit',numpy=np.__version__,opencv=cv2.__version__))


def target(r):
    if r['label'] in ('noise','vegetation-like','closed-contour'): return 1
    if r['label'] in ('poi','numeric','uncertain','protected-symbol'): return -1
    return 0


def train(x,y):
    # Fixed RBF kernel, class-balanced ridge regression. Scores are NOT probabilities.
    dist=np.maximum(0,2-2*x@x.T)
    bandwidth=max(.05,float(np.median(dist[np.triu_indices(len(x),1)])))
    kernel=np.exp(-dist/bandwidth)
    weight=np.array([len(y)/(2*np.sum(y==v)) for v in y])
    alpha=np.linalg.solve(kernel+np.diag(PARAMS['ridge']/weight),y)
    return x,y,bandwidth,alpha


def predict(model,x):
    base,y,bandwidth,alpha=model
    dist=np.maximum(0,2-2*x@base.T)
    score=np.exp(-dist/bandwidth)@alpha
    ratio=np.min(dist[:,y==1],axis=1)/np.maximum(1e-8,np.min(dist[:,y==-1],axis=1))
    return score,ratio


def develop():
    if (OUT/'locked-model.json').exists(): raise RuntimeError('Do not retune a locked experiment')
    rows=read(OUT/'dataset.json'); arrays=np.load(OUT/'features.npz')
    # Deduplicate overlapping findings; conflicting labels abstain and exclude from fit.
    groups={}
    for i,r in enumerate(rows):
        if r['split']=='development': groups.setdefault(r['physical_group'],[]).append(i)
    ids=[min(v) for v in groups.values() if len({target(rows[i]) for i in v})==1]
    excluded=[v for v in groups.values() if len({target(rows[i]) for i in v})>1]
    ids=np.array(ids); y=np.array([target(rows[i]) for i in ids]); results={}; models={}
    for name in PARAMS['features']:
        x=arrays[name][ids]; oof=[]
        for block in sorted({rows[i]['block'] for i in ids}):
            test=np.array([j for j,i in enumerate(ids) if rows[i]['block']==block])
            # Buffer every held-out crop by one tile; no adjacent-tile memorization.
            fit=np.array([j for j,i in enumerate(ids) if rows[i]['block']!=block and not any(near(rows[i],rows[ids[k]]) for k in test)])
            if len(set(y[fit]))<2: raise RuntimeError('Insufficient classes for spatial calibration')
            scores,ratios=predict(train(x[fit],y[fit]),x[test])
            for j,s,q in zip(test,scores,ratios):
                oof.append(dict(id=rows[ids[j]]['id'], index=int(ids[j]),label=rows[ids[j]]['label'],target=int(y[j]),score=float(s),ratio=float(q),fit_count=len(fit),block=block))
        threshold=max(r['score'] for r in oof if r['target']==-1)+PARAMS['margin']
        for r in oof:
            r['reject']=r['score']>threshold
            r['guarded_reject']=r['reject'] and r['ratio']<PARAMS['guard_ratio']
        results[name]=dict(threshold=threshold,oof=oof,noise_rejected=sum(r['reject'] and r['target']==1 for r in oof),guarded_noise_rejected=sum(r['guarded_reject'] and r['target']==1 for r in oof),protected_rejected=sum(r['reject'] and r['target']==-1 for r in oof))
        models[name]=train(x,y)
    write('development.json',dict(groups=len(ids),conflicting_groups=excluded,results=results))
    # Lock both surviving safe methods before any unseen labels are evaluated.
    write('locked-model.json',dict(parameters=PARAMS,dataset_sha256=digest(OUT/'dataset.json'),feature_sha256=digest(OUT/'features.npz'),code_sha256=digest(__file__),fit_indices=ids.tolist(),thresholds={k:v['threshold'] for k,v in results.items()},fit_labels=y.tolist()))
    print(json.dumps({k:{a:b for a,b in v.items() if a!='oof'} for k,v in results.items()},indent=2))


def evaluate():
    lock=read(OUT/'locked-model.json'); rows=read(OUT/'dataset.json'); arrays=np.load(OUT/'features.npz')
    assert digest(OUT/'dataset.json')==lock['dataset_sha256']
    assert digest(OUT/'features.npz')==lock['feature_sha256']
    labels=read(OUT/'new-visual-labels.json') if (OUT/'new-visual-labels.json').exists() else {'labels':{}}
    output={}
    for name in PARAMS['features']:
        ids=np.array(lock['fit_indices']); start=time.perf_counter()
        model=train(arrays[name][ids],np.array(lock['fit_labels'])); fit_ms=(time.perf_counter()-start)*1000
        samples=[]; times=[]
        for i,r in enumerate(rows):
            if r['split']=='development': continue
            t=time.perf_counter(); score,ratio=predict(model,arrays[name][i:i+1]); times.append((time.perf_counter()-t)*1000)
            r=r.copy(); r['label']=labels['labels'].get(str(r['id']),r['label'])
            s=float(score[0]); q=float(ratio[0]); reject=s>lock['thresholds'][name]
            samples.append(dict(id=r['id'],split=r['split'],label=r['label'],target=target(r),physical_group=r['physical_group'],score=s,ratio=q,reject=reject,guarded_reject=reject and q<PARAMS['guard_ratio']))
        counts={}
        for split in sorted({r['split'] for r in samples}):
            counts[split]={}
            for label in sorted({r['label'] for r in samples if r['split']==split}):
                rr=[r for r in samples if r['split']==split and r['label']==label]
                counts[split][label]=dict(total=len(rr),reject=sum(r['reject'] for r in rr),guarded_reject=sum(r['guarded_reject'] for r in rr))
        output[name]=dict(counts=counts,samples=samples,fit_ms=fit_ms,timing=dict(mean=statistics.mean(times),median=statistics.median(times),p95=float(np.percentile(times,95)),maximum=max(times),unit='ms/crop prediction only',raw=times))
    write('evaluation.json',output)
    print(json.dumps({k:v['counts'] for k,v in output.items()},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['freeze','features','develop','evaluate'])
    globals()[parser.parse_args().stage]()
