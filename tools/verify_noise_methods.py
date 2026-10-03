"""Reproduce spatial baseline, method scores and serialized state independently."""
import time
import cv2
import numpy as np
from PIL import Image,ImageDraw
from .contour_learner_data import ROOT,read,write,sha,near
from .contour_learner_trial import fit,predict
from .noise_methods_features import OUT,BASE,native_window
from .noise_methods_trial import METHODS,score_method,margin,patch_score,subspace_fit,subspace_score,recurrence,outside_positions


def invariants():
    box=[20,20,28,28];mask=outside_positions((48,48),box,8)
    assert not mask[20,20] and not mask[17,17] and mask[10,10]
    assert all(x+8<=18 or x>=30 or y+8<=18 or y>=30 for y,x in np.argwhere(mask))
    x=np.array([[1,0,0],[0,1,0]],np.float32);y=np.array([1,0])
    assert margin(x,x,y)[0]>.99 and margin(x,x,y)[1]<.01
    assert patch_score([x[:1]],x[:1])[0]>patch_score([x[1:]],x[:1])[0]
    center,basis=subspace_fit(np.array([[1,0,0],[-1,0,0]],np.float32))
    assert subspace_score(np.array([[0,0,0]],np.float32),center,basis)[0]>subspace_score(np.array([[0,1,0]],np.float32),center,basis)[0]
    im=Image.new('RGB',(192,192),'white');dr=ImageDraw.Draw(im)
    for yy in range(4,192,8):dr.line((0,yy,191,yy),fill='black',width=1)
    repeating,qn=recurrence(im,[88,88,104,104]);assert qn>0 and repeating>.9
    blank=recurrence(Image.new('RGB',(192,192),'white'),[88,88,104,104]);assert blank==(0,0)
    small=Image.new('RGB',(192,192),'white');ImageDraw.Draw(small).rectangle((80,80,87,87),fill='black')
    crop,bb=native_window(small,[80,80,88,88]);assert bb[2]-bb[0]==8 and crop.size==(196,196)
    return dict(checks=7,local_exact_repetition_score=repeating,blank_abstains=True,self_match_excluded=True,native_size_preserved=True)


def main():
    start=time.perf_counter();checks=invariants()
    lock=read(OUT/'model-lock.json');featurelock=read(OUT/'feature-lock.json')
    assert sha(ROOT/'tools/noise_methods_trial.py')==lock['code_sha256']
    assert sha(ROOT/'tools/noise_methods_features.py')==featurelock['code_sha256']
    assert sha(OUT/'dino-features.npz')==featurelock['arrays_sha256']
    assert sha(BASE/'folds.json')==lock['folds_sha256'] and sha(BASE/'holdout-inputs.json')==lock['holdout_sha256']
    rows=read(BASE/'training.json');guards=read(BASE/'guards.json');n=len(rows)
    folds=read(BASE/'folds.json');y=np.array([int(r['negative']) for r in rows],np.int32)
    assert sorted(i for f in folds for i in f['test'])==list(range(n))
    for f in folds:assert not any(near(rows[a],rows[b]) for a in f['fit'] for b in f['test'])
    arr=np.load(BASE/'features.npz');old=read(BASE/'development-predictions.json')['appearance-structure']
    baseline=arr['appearance-structure'];oof=np.zeros(n)
    for f in folds:oof[f['test']]=predict(fit(baseline[f['fit']],y[f['fit']]),baseline[f['test']])
    np.testing.assert_array_equal(oof,[r['score'] for r in old['oof']])
    arrays=np.load(OUT/'dino-features.npz');x=arrays['vectors'][:n];gx=arrays['vectors'][n:]
    patches=[arrays[f'p{i}'] for i in range(n)];gp=[arrays[f'p{i}'] for i in range(n,n+len(guards))]
    structure=baseline[:,-18:];gs=np.load(BASE/'guard-features.npz')['appearance-structure'][:,-18:]
    expected=read(OUT/'development-predictions.json');results={}
    for m in METHODS:
        if m=='local-recurrence':
            values=[]
            for r in rows+guards:
                with Image.open(ROOT/r['context']) as im:values.append(recurrence(im.convert('RGB'),r['context_box'])[0])
            oof=np.array(values[:n]);guard=np.array(values[n:])
        else:
            oof=np.zeros(n)
            for f in folds:
                tr,te=np.array(f['fit']),np.array(f['test'])
                oof[te],_,_=score_method(m,x[tr],y[tr],[patches[i] for i in tr],x[te],[patches[i] for i in te],structure[te],structure[tr])
            if m=='dino-structure-rf':guard=predict(cv2.ml.RTrees_load(str(OUT/f'{m}.xml')),np.column_stack([gx,gs]).astype(np.float32))
            else:
                state=np.load(OUT/f'{m}.npz')
                if m=='example-margin':guard=margin(gx,state['x'],state['y'])
                elif m=='contour-patch-memory':guard=patch_score(gp,state['bank'])
                else:guard=subspace_score(gx,state['center'],state['basis'])
        np.testing.assert_allclose(oof,[r['score'] for r in expected[m]['oof']],atol=1e-7,rtol=0)
        np.testing.assert_allclose(guard,[r['score'] for r in expected[m]['guards']],atol=1e-7,rtol=0)
        results[m]='all OOF scores and saved-state guard scores reproduced'
    write(OUT/'verification.json',dict(invariants=checks,baseline='218 spatial OOF scores exactly reproduced',methods=results,
        hashes='Feature/model source, arrays, split and holdout hashes match',folds='Five folds cover each target once, fit/test two-tile exclusion verified',
        seconds=time.perf_counter()-start,code_sha256=sha(ROOT/'tools/verify_noise_methods.py')))
    print('Baseline, all five pilots, serialization, spatial separation and seven invariants verified.')


if __name__=='__main__':main()
