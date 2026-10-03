"""Fixed mechanism pilots on frozen spatial folds; no production or DB writes."""
import math
import time
import cv2
import numpy as np
from PIL import Image
from .contour_learner_data import ROOT,read,write,sha,near
from .contour_learner_trial import fit,predict
from .noise_methods_features import OUT,BASE,native_window

METHODS=['dino-structure-rf','example-margin','contour-patch-memory','contour-subspace','local-recurrence']


def distances(query,bank):
    return np.clip(1-query@bank.T,0,2)


def margin(query,x,y):
    values=[]
    for label in (0,1):
        d=distances(query,x[y==label]);k=min(3,d.shape[1])
        values.append(np.partition(d,k-1,axis=1)[:,:k].mean(1))
    return values[0]/np.maximum(values[0]+values[1],1e-8)


def patch_score(queries,bank):
    # Conservatively keep a target if its least typical 10% of patches stand out.
    return np.array([1-float(np.quantile(distances(p,bank).min(1),.9))/2 for p in queries])


def subspace_fit(x):
    center=x.mean(0);_,_,v=np.linalg.svd(x-center,full_matrices=False)
    return center,v[:min(16,len(x)-1)]


def subspace_score(x,center,basis):
    d=x-center;residual=d-(d@basis.T)@basis
    return np.exp(-np.sum(residual*residual,axis=1)/.1)


def outside_positions(shape,box,size):
    """A search template cannot overlap the target or its two-pixel margin."""
    h,w=shape;a,b,c,d=box;yy,xx=np.indices((h-size+1,w-size+1))
    return (xx+size<=a-2)|(xx>=c+2)|(yy+size<=b-2)|(yy>=d+2)


def recurrence(im,box):
    im,box=native_window(im,box);gray=np.asarray(im.convert('L'),dtype=np.float32)/255
    ink=np.maximum(cv2.GaussianBlur(gray,(0,0),3)-gray,0)
    a,b,c,d=box;values=[]
    for size in (8,16):
        centers=[(x,y) for y in np.arange(b+(d-b)/max(1,math.ceil((d-b)/size))/2,d,max(1,(d-b)/max(1,math.ceil((d-b)/size))))
                 for x in np.arange(a+(c-a)/max(1,math.ceil((c-a)/size))/2,c,max(1,(c-a)/max(1,math.ceil((c-a)/size))))]
        take=np.unique(np.linspace(0,len(centers)-1,min(25,len(centers)),dtype=int))
        allowed=outside_positions(ink.shape,box,size)
        if not allowed.any():continue
        for i in take:
            x,y=centers[i];x=int(np.clip(round(x)-size//2,0,196-size));y=int(np.clip(round(y)-size//2,0,196-size))
            query=ink[y:y+size,x:x+size]
            if np.mean(query>18/255)<.04:continue
            result=cv2.matchTemplate(ink,query,cv2.TM_SQDIFF_NORMED)
            values.append(float(np.sqrt(np.clip(result[allowed].min(),0,1))))
    return (1-float(np.quantile(values,.9)) if values else 0),len(values)


def score_method(method,x,y,patches,sx,queries,sstructure,structure):
    if method=='dino-structure-rf':
        model=fit(np.column_stack([x,structure]).astype(np.float32),y)
        return predict(model,np.column_stack([sx,sstructure]).astype(np.float32)),model,None
    if method=='example-margin':return margin(sx,x,y),None,dict(x=x,y=y)
    if method=='contour-patch-memory':
        bank=np.concatenate([p for p,yy in zip(patches,y) if yy==1])
        return patch_score(queries,bank),None,dict(bank=bank)
    if method=='contour-subspace':
        center,basis=subspace_fit(x[y==1])
        return subspace_score(sx,center,basis),None,dict(center=center,basis=basis)
    raise ValueError(method)


def main():
    if (OUT/'model-lock.json').exists():raise RuntimeError('Locked experiment; use verification, not overwrite')
    cv2.setNumThreads(1)
    # Record exact score definitions before producing any method's evaluation.
    write(OUT/'score-definitions.json',dict(methods=METHODS,
        margin='mean3 cosine distance to protected bank / (mean3 protected + mean3 noise distance)',
        patches='1 - q90(nearest cosine distance to training contour token bank)/2; all query target tokens',
        subspace='rank16 centered SVD of contour descriptors only; exp(-squared residual/.1)',
        recurrence='Positive sigma3 local ink residual; 8/16 pixel nonrotated templates; at most25 target centers/scale; skip <4% ink above18/255; minimum SQDIFF_NORMED outside target+2px; 1-q90(sqrt(mismatch)). No valid query -> score0 (retain).',
        threshold='max protected spatial OOF score + .025, strictly greater',
        comparison='RF changes only visual representation; all other methods are separate algorithm comparisons, not additive ablations',
        inference_resources='Offline pilot only; measure GPU feature extraction and CPU scoring separately; no online latency claim'))
    lock=read(OUT/'feature-lock.json')
    for name,key in [('dino-features.npz','arrays_sha256')]:assert sha(OUT/name)==lock[key]
    assert sha(ROOT/'tools/noise_methods_features.py')==lock['code_sha256']
    rows=read(BASE/'training.json');guards=read(BASE/'guards.json');n=len(rows)
    assert sha(BASE/'training.json')==lock['training_sha256'] and sha(BASE/'guards.json')==lock['guards_sha256']
    splits=read(BASE/'folds.json');hold=read(BASE/'holdout-inputs.json')
    for s in splits:assert not any(near(rows[i],rows[j]) for i in s['fit'] for j in s['test'])
    assert not any(near(a,b) for a in rows for b in hold)
    f=np.load(OUT/'dino-features.npz');allx=f['vectors'];x=allx[:n];gx=allx[n:]
    patches=[f[f'p{i}'] for i in range(n)];gp=[f[f'p{i}'] for i in range(n,len(allx))]
    structure=np.load(BASE/'features.npz')['appearance-structure'][:,-18:]
    gs=np.load(BASE/'guard-features.npz')['appearance-structure'][:,-18:]
    y=np.array([int(r['negative']) for r in rows],np.int32)
    outputs={};summary={};models={}
    for method in METHODS:
        started=time.perf_counter();scores=np.zeros(n);times=[]
        if method=='local-recurrence':
            rs=[];qt=[]
            for row in rows+guards:
                path=ROOT/row['context'];assert sha(path)==row['context_sha256']
                with Image.open(path) as im:im=im.convert('RGB')
                start=time.perf_counter();score,count=recurrence(im,row['context_box'])
                times.append((time.perf_counter()-start)*1000);rs.append(score);qt.append(count)
            scores=np.array(rs[:n]);guard_scores=np.array(rs[n:]);state=dict(scores=np.array(rs),queries=np.array(qt))
            np.savez_compressed(OUT/f'{method}.npz',**state)
        else:
            for s in splits:
                tr,te=np.array(s['fit']),np.array(s['test'])
                values,_,_=score_method(method,x[tr],y[tr],[patches[i] for i in tr],x[te],[patches[i] for i in te],structure[te],structure[tr])
                scores[te]=values
            start=time.perf_counter()
            guard_scores,model,state=score_method(method,x,y,patches,gx,gp,gs,structure)
            times=[(time.perf_counter()-start)*1000]
            if model is not None:model.save(str(OUT/f'{method}.xml'))
            else:np.savez_compressed(OUT/f'{method}.npz',**state)
        threshold=float(scores[y==0].max()+.025);hits=scores>threshold;gh=guard_scores>threshold
        byedition={source:dict(contours=sum(bool(r['negative']) for r in rows if r['source']==source),
            hits=sum(bool(h and r['negative']) for r,h in zip(rows,hits) if r['source']==source)) for source in sorted({r['source'] for r in rows})}
        hits1924=sum(e['hits'] for k,e in byedition.items() if '1924' in k)
        eligible=int(np.sum(hits & (y==1)))>=24 and not gh.any() and hits1924>2
        outputs[method]=dict(oof=[dict(id=r['id'],score=float(v),negative=bool(yy),label=r['label'],reject=bool(h)) for r,v,yy,h in zip(rows,scores,y,hits)],
            guards=[dict(id=r['id'],score=float(v),label=r['label'],reject=bool(h)) for r,v,h in zip(guards,guard_scores,gh)])
        summary[method]=dict(threshold=threshold,contours=int(y.sum()),contour_hits=int(np.sum(hits & (y==1))),
            protected=int(np.sum(y==0)),protected_hits=int(np.sum(hits & (y==0))),guard_count=len(guards),guard_hits=int(gh.sum()),
            by_edition=byedition,eligible=bool(eligible),wall_ms=(time.perf_counter()-started)*1000,
            timing_ms=times,timing_scope='Per sample image processing, excludes decode' if method=='local-recurrence' else 'Full fit plus58 guard scores, excludes frozen feature extraction',
            decision='eligible for frozen holdout' if eligible else 'reject before holdout')
        suffix='xml' if method=='dino-structure-rf' else 'npz'
        models[method]=dict(threshold=threshold,eligible=bool(eligible),state_sha256=sha(OUT/f'{method}.{suffix}'))
        print(method,summary[method]['contour_hits'],byedition,'guards',int(gh.sum()),'threshold',threshold,flush=True)
    write(OUT/'development-predictions.json',outputs);write(OUT/'development-summary.json',summary)
    write(OUT/'model-lock.json',dict(models=models,code_sha256=sha(ROOT/'tools/noise_methods_trial.py'),
        feature_lock_sha256=sha(OUT/'feature-lock.json'),folds_sha256=sha(BASE/'folds.json'),
        definitions_sha256=sha(OUT/'score-definitions.json'),holdout_sha256=sha(BASE/'holdout-inputs.json'),
        contract_sha256=sha(OUT/'contract.json'),numpy=np.__version__,opencv=cv2.__version__))


if __name__=='__main__':main()
