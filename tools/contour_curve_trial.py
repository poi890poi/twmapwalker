"""Paired experiment: frozen contour learner plus independent curve-residual features."""
import math
import time
from collections import Counter

import cv2
import numpy as np
from PIL import Image

from .contour_learner_data import ROOT,sha,read,write,sheets
from .contour_learner_trial import fit,predict,extract as baseline_extract
from .contour_curve_features import extract,PARAMETERS,NAMES

BASE=ROOT/'evidence/contour-learner'
OUT=ROOT/'evidence/contour-curves'


def curve_features(rows):
    values=[];telemetry=[]
    for r in rows:
        path=ROOT/r['context'];assert sha(path)==r['context_sha256']
        with Image.open(path) as source:im=source.convert('RGB')
        start=time.perf_counter();v,info=extract(im,r['context_box']);elapsed=(time.perf_counter()-start)*1000
        values.append(v);telemetry.append(dict(id=r['id'],features=info,feature_ms=elapsed))
    return np.stack(values),telemetry


def main():
    OUT.mkdir(exist_ok=False)
    write(OUT/'contract.json',dict(type='Offline feature experiment; production unchanged pending validation',
        causal_input='Target box and native map pixels. Curves inferred with the target and 4px halo erased. Labels and coordinates only for evaluation/splitting.',
        change='Append 14 curve-explanation/residual measurements to the frozen appearance-structure feature set. Same rows, spatial folds, forest parameters and calibration margin.',
        acceptance='At least 25% development contours caught, zero reused protection flags, and improvement over the baseline on 1924 contours. Then test the untouched 48-target holdout with no threshold changes. Automatic suppression requires at least 25% held-out contour removal, zero protected flags and coverage of names, numbers, Kana and rare-symbol protection probes.',
        risks='Neighboring curves can accidentally explain text strokes; unmodelled curve families abstain. Zero OOF protected flags is imposed by calibration and is not independent safety evidence.',
        limits='Local quadratic approximation, assistant visual labels, small and enriched sample; no calibrated probability or population precision claim.',
        feature_parameters=PARAMETERS,feature_names=NAMES))
    rows=read(BASE/'training.json');guards=read(BASE/'guards.json');folds=read(BASE/'folds.json')
    base=np.load(BASE/'features.npz')['appearance-structure'];guardbase=np.load(BASE/'guard-features.npz')['appearance-structure']
    extra,telemetry=curve_features(rows);gextra,gtelemetry=curve_features(guards)
    x=np.column_stack([base,extra]);gx=np.column_stack([guardbase,gextra])
    np.savez_compressed(OUT/'features.npz',train=x,guards=gx)
    write(OUT/'feature-telemetry.json',dict(development=telemetry,guards=gtelemetry))
    y=np.array([int(r['negative']) for r in rows],dtype=np.int32);scores=np.zeros(len(rows))
    for fold in folds:
        scores[fold['test']]=predict(fit(x[fold['fit']],y[fold['fit']]),x[fold['test']])
    threshold=float(np.max(scores[y==0])+.025)
    start=time.perf_counter();model=fit(x,y);fit_ms=(time.perf_counter()-start)*1000
    model.save(str(OUT/'model.xml'));gs=predict(model,gx)
    hits=scores>threshold;ghits=gs>threshold
    predictions=dict(development=[dict(id=r['id'],label=r['label'],negative=bool(yy),score=float(s),reject=bool(h)) for r,yy,s,h in zip(rows,y,scores,hits)],
        guards=[dict(id=r['id'],label=r['label'],score=float(s),reject=bool(h)) for r,s,h in zip(guards,gs,ghits)])
    write(OUT/'predictions.json',predictions)
    editions={edition:dict(contours=sum(r['negative'] and r['source']==edition for r in rows),
        hits=sum(bool(hit) and r['negative'] and r['source']==edition for r,hit in zip(rows,hits))) for edition in sorted({r['source'] for r in rows})}
    eligible=int(np.sum(hits&(y==1)))>=math.ceil(.25*y.sum()) and not ghits.any() and editions['JM50K_1924_new']['hits']>2
    summary=dict(threshold=threshold,contours=int(y.sum()),contour_hits=int(np.sum(hits&(y==1))),
        protected=int(np.sum(y==0)),protected_hits=int(np.sum(hits&(y==0))),guard_count=len(guards),guard_hits=int(ghits.sum()),
        editions=editions,fit_ms=fit_ms,decision='eligible for frozen holdout' if eligible else 'reject before holdout',
        curve_available_contours=sum(v['features']['available'] and r['negative'] for v,r in zip(telemetry,rows)),
        curve_available_protected=sum(v['features']['available'] and not r['negative'] for v,r in zip(telemetry,rows)))
    write(OUT/'summary.json',summary)
    write(OUT/'lock.json',dict(eligible=eligible,threshold=threshold,model_sha256=sha(OUT/'model.xml'),
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in [ROOT/'tools/contour_curve_features.py',ROOT/'tools/contour_curve_trial.py',ROOT/'tools/contour_learner_trial.py']},
        inputs={p.relative_to(ROOT).as_posix():sha(p) for p in [BASE/'training.json',BASE/'guards.json',BASE/'folds.json',BASE/'features.npz',BASE/'guard-features.npz',BASE/'holdout-inputs.json']},
        features_sha256=sha(OUT/'features.npz')))
    print(__import__('json').dumps(summary,indent=2),flush=True)


def holdout():
    lock=read(OUT/'lock.json')
    assert lock['eligible'],'Stop a failed candidate before held-out evaluation'
    assert not (OUT/'holdout-predictions.json').exists()
    for name,digest in lock['sources'].items():assert sha(ROOT/name)==digest
    for name,digest in lock['inputs'].items():assert sha(ROOT/name)==digest
    rows=read(BASE/'holdout-inputs.json');base=[]
    for r in rows:
        with Image.open(ROOT/r['context']) as im:base.append(baseline_extract(im,r['context_box'])['appearance-structure'])
    extra,telemetry=curve_features(rows);x=np.column_stack([np.stack(base),extra])
    assert sha(OUT/'model.xml')==lock['model_sha256']
    scores=predict(cv2.ml.RTrees_load(str(OUT/'model.xml')),x)
    write(OUT/'holdout-predictions.json',[dict(id=r['id'],index=r['index'],score=float(s),reject=bool(s>lock['threshold'])) for r,s in zip(rows,scores)])
    write(OUT/'holdout-feature-telemetry.json',telemetry)
    write(OUT/'holdout-lock.json',dict(model_lock_sha256=sha(OUT/'lock.json'),predictions_sha256=sha(OUT/'holdout-predictions.json')))
    sheets(rows,OUT,'holdout')
    print('Held-out predictions saved before showing pixels; no scores displayed.',flush=True)


if __name__=='__main__':
    import sys
    (holdout if len(sys.argv)>1 and sys.argv[1]=='holdout' else main)()
