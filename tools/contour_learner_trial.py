"""Two fixed random-forest feature sets; spatial OOF calibration and locked holdout."""
import math
import time
from collections import Counter

import cv2
import numpy as np
from PIL import Image,ImageOps

from .contour_learner_data import ROOT,OUT,sha,read,write,block,order,near,sheets
from .contour_frequency_trial import spectrum
from .contour_topology_trial import features as topology

HOG=cv2.HOGDescriptor((32,32),(16,16),(8,8),(8,8),9)
PARAMS=dict(trees=160,depth=8,min_samples=3,seed=33073,folds=5,threshold_margin=.025,
            methods=['appearance','appearance-structure'],class_balance='Inverse frequency class priors',
            structure='Target width/height; target and context spectral fractions/entropy; skeleton continuity/branches/endpoints and neighbor orientation',
            appearance='Aspect-preserving 32x32 HOG of target + context; 4x4 local contrast and ink coverage grids for each',
            decision='Strictly greater than maximum spatial OOF protected score plus .025; votes are not calibrated probabilities.')


def appearance(im):
    thumb=ImageOps.contain(im.convert('L'),(32,32),Image.Resampling.LANCZOS)
    pad=Image.new('L',(32,32),255);pad.paste(thumb,((32-thumb.width)//2,(32-thumb.height)//2))
    a=np.asarray(pad)
    hog=HOG.compute(a).ravel()
    gray=np.asarray(im.convert('L'),dtype=np.float32)/255
    residual=cv2.GaussianBlur(gray,(0,0),8)-gray
    return np.concatenate([hog,cv2.resize(residual,(4,4),interpolation=cv2.INTER_AREA).ravel(),
                           cv2.resize((residual>18/255).astype(np.float32),(4,4),interpolation=cv2.INTER_AREA).ravel()])


def extract(im,box):
    a,b,c,d=box
    mark=im.crop((math.floor(a)-4,math.floor(b)-4,math.ceil(c)+4,math.ceil(d)+4))
    base=np.concatenate([appearance(mark),appearance(im)])
    ms,cs=spectrum(mark),spectrum(im);tp=topology(im,box)
    scalar=[math.log1p(c-a),math.log1p(d-b)]
    for spec in (ms,cs):scalar.extend([float(spec['available'])]+[spec.get(k,0) for k in ('axis_fraction','two_axes_fraction','entropy')])
    scalar.extend([float(tp['available'])]+[tp.get(k,0) for k in ('target_nodes','continuing_fraction','internal_endpoints','internal_branch_fraction','neighboring_long_components','target_coherence','neighbor_alignment')])
    return dict(appearance=base.astype(np.float32),**{'appearance-structure':np.concatenate([base,scalar]).astype(np.float32)})


def fit(x,y,seed=33073):
    cv2.setNumThreads(1);cv2.setRNGSeed(seed)
    model=cv2.ml.RTrees_create();model.setMaxDepth(8);model.setMinSampleCount(3)
    model.setMaxCategories(2);model.setActiveVarCount(0);model.setCalculateVarImportance(True)
    model.setPriors(np.array([len(y)/(2*np.sum(y==v)) for v in (0,1)],dtype=np.float32))
    model.setTermCriteria((cv2.TERM_CRITERIA_MAX_ITER,160,0))
    assert model.train(x,cv2.ml.ROW_SAMPLE,y.astype(np.int32))
    return model


def predict(model,x):
    votes=model.getVotes(x,0)
    index=int(np.flatnonzero(votes[0]==1)[0])
    return votes[1:,index]/votes[1:].sum(axis=1)


def assemble():
    base=read(OUT/'base-training.json');labels=read(OUT/'new-protection-labels.json')
    inverse={i:lab for lab,indices in labels.items() if isinstance(indices,list) for i in indices}
    assert len(inverse)==96 and sum(len(v) for v in labels.values() if isinstance(v,list))==96
    for r in read(OUT/'new-protection-inputs.json'):
        lab=inverse[r['index']]
        base.append({**r,'label':lab,'negative':lab=='contour-fragment','origin':'new-protection'})
    assert len({str(r['id']) for r in base})==len(base)
    # All old positive probes stay out of fitting and calibration; remove exact training IDs.
    old=read(ROOT/'evidence/noise-verifier/dataset.json')
    updated=read(ROOT/'evidence/noise-verifier/new-visual-labels.json')['labels']
    guards=[]
    for r in old:
        lab=updated.get(str(r['id']),r['label'])
        if lab not in ('poi','numeric','protected-symbol'):continue
        assert str(r['id']) not in {str(v['id']) for v in base}
        guards.append({**r,'context':(ROOT/'evidence/noise-verifier'/r['crop']).relative_to(ROOT).as_posix(),
            'context_box':r['crop_box'],'context_sha256':r['sha256'],'label':lab,'negative':False,'origin':'reused-protection'})
    write(OUT/'training.json',base);write(OUT/'guards.json',guards)
    return base,guards


def all_features(rows):
    vectors={k:[] for k in PARAMS['methods']};times=[]
    for row in rows:
        path=ROOT/row['context'];assert sha(path)==row['context_sha256']
        with Image.open(path) as source:im=source.convert('RGB')
        start=time.perf_counter();f=extract(im,row['context_box']);times.append((time.perf_counter()-start)*1000)
        for key,value in f.items():vectors[key].append(value)
    return {key:np.stack(value) for key,value in vectors.items()},times


def main():
    if (OUT/'model-lock.json').exists():raise RuntimeError('Preserve locked models and thresholds')
    write(OUT/'parameters.json',PARAMS)
    rows,guards=assemble();x,times=all_features(rows);gx,gtimes=all_features(guards)
    np.savez_compressed(OUT/'features.npz',**x);np.savez_compressed(OUT/'guard-features.npz',**gx)
    y=np.array([int(r['negative']) for r in rows],dtype=np.int32)
    fold=np.array([int(order('fold:'+block(r))[:8],16)%5 for r in rows])
    split=[]
    for k in range(5):
        test=np.flatnonzero(fold==k)
        train=np.array([i for i,r in enumerate(rows) if fold[i]!=k and not any(near(r,rows[j]) for j in test)])
        assert len(set(y[train]))==2
        split.append(dict(fold=k,fit=train.tolist(),test=test.tolist()))
    write(OUT/'folds.json',split)
    summary={};outputs={};locks={}
    for method in PARAMS['methods']:
        scores=np.zeros(len(rows))
        for s in split:scores[s['test']]=predict(fit(x[method][s['fit']],y[s['fit']]),x[method][s['test']])
        threshold=float(np.max(scores[y==0])+.025)
        start=time.perf_counter();model=fit(x[method],y);fit_ms=(time.perf_counter()-start)*1000
        model.save(str(OUT/f'{method}.xml'))
        gs=predict(model,gx[method]);hits=scores>threshold;guardhits=gs>threshold
        useful=int(np.sum(hits & (y==1)))
        eligible=useful>=math.ceil(.25*np.sum(y==1)) and not guardhits.any()
        outputs[method]=dict(oof=[dict(id=r['id'],score=float(s),negative=bool(yy),label=r['label'],reject=bool(h)) for r,s,yy,h in zip(rows,scores,y,hits)],
            guards=[dict(id=r['id'],score=float(s),label=r['label'],reject=bool(h)) for r,s,h in zip(guards,gs,guardhits)])
        summary[method]=dict(threshold=threshold,contours=int(np.sum(y)),contour_hits=useful,
            protected=int(np.sum(y==0)),protected_hits=int(np.sum(hits & (y==0))),
            guard_count=len(guards),guard_hits=int(guardhits.sum()),fit_ms=fit_ms,
            decision='eligible for frozen holdout' if eligible else 'reject before holdout')
        locks[method]=dict(threshold=threshold,model_sha256=sha(OUT/f'{method}.xml'),eligible=eligible)
    write(OUT/'development-predictions.json',outputs);write(OUT/'development-summary.json',summary)
    write(OUT/'model-lock.json',dict(models=locks,code_sha256=sha(ROOT/'tools/contour_learner_trial.py'),
        training_sha256=sha(OUT/'training.json'),features_sha256=sha(OUT/'features.npz'),
        holdout_sha256=sha(OUT/'holdout-inputs.json'),parameters_sha256=sha(OUT/'parameters.json'),
        labels_sha256=sha(OUT/'new-protection-labels.json')))
    write(OUT/'timing.json',dict(feature_ms=times,guard_feature_ms=gtimes,scope='Feature extraction excludes decode and I/O; both feature sets computed together',
        numpy=np.__version__,opencv=cv2.__version__))
    print(__import__('json').dumps(summary,indent=2))


def holdout():
    lock=read(OUT/'model-lock.json')
    assert sha(ROOT/'tools/contour_learner_trial.py')==lock['code_sha256']
    assert sha(OUT/'holdout-inputs.json')==lock['holdout_sha256']
    if (OUT/'holdout-predictions.json').exists():raise RuntimeError('Preserve held-out predictions')
    survivors={k:v for k,v in lock['models'].items() if v['eligible']}
    if not survivors:raise RuntimeError('No surviving model: stop before consuming holdout')
    rows=read(OUT/'holdout-inputs.json');x,times=all_features(rows);results={}
    for method,entry in survivors.items():
        assert sha(OUT/f'{method}.xml')==entry['model_sha256']
        model=cv2.ml.RTrees_load(str(OUT/f'{method}.xml'))
        scores=predict(model,x[method]);results[method]=[dict(id=r['id'],index=r['index'],score=float(s),reject=bool(s>entry['threshold'])) for r,s in zip(rows,scores)]
    write(OUT/'holdout-predictions.json',results)
    write(OUT/'holdout-lock.json',dict(predictions_sha256=sha(OUT/'holdout-predictions.json'),model_lock_sha256=sha(OUT/'model-lock.json')))
    sheets(rows,OUT,'holdout')
    print('Held-out predictions locked before contact sheets or labels. No scores displayed.')


if __name__=='__main__':
    import sys
    (holdout if len(sys.argv)>1 and sys.argv[1]=='holdout' else main)()
