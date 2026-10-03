"""Replay and expose both curve-explanation experiments, including negative results."""
import time
from collections import Counter

import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageOps

from .contour_learner_data import ROOT,sha,read,write,near,block
from .contour_learner_trial import fit,predict
from . import contour_curve_trial as v1
from . import contour_curve_trial_v2 as v2
from . import contour_curve_features as f1
from . import contour_curve_features_v2 as f2

BASE=ROOT/'evidence/contour-learner'


def verify(trial,feature):
    folder=trial.OUT;lock=read(folder/'lock.json');rows=read(BASE/'training.json');guards=read(BASE/'guards.json')
    for field in ('sources','inputs'):
        for path,digest in lock[field].items():assert sha(ROOT/path)==digest
    assert sha(folder/'model.xml')==lock['model_sha256']
    assert sha(folder/'features.npz')==lock['features_sha256']
    saved=np.load(folder/'features.npz');original=read(folder/'feature-telemetry.json')
    extra,t=trial.curve_features(rows);gextra,gt=trial.curve_features(guards)
    x=np.column_stack([np.load(BASE/'features.npz')['appearance-structure'],extra])
    gx=np.column_stack([np.load(BASE/'guard-features.npz')['appearance-structure'],gextra])
    assert np.array_equal(x,saved['train']);assert np.array_equal(gx,saved['guards'])
    for new,old in [(t,original['development']),(gt,original['guards'])]:
        assert [r['features'] for r in new]==[r['features'] for r in old]
    # Manipulate real target pixels: they must not steer the inferred background curves.
    causal=0
    for r in rows:
        with Image.open(ROOT/r['context']) as im:im=im.convert('RGB')
        info,tube,_=feature.infer_curves(im,r['context_box'])
        changed=np.array(im);changed[feature.mask_box(changed.shape[:2],r['context_box'])]=0
        other,othertube,_=feature.infer_curves(Image.fromarray(changed),r['context_box'])
        assert info==other and np.array_equal(tube,othertube)
        causal+=1
    folds=read(BASE/'folds.json');held=read(BASE/'holdout-inputs.json');y=np.array([int(r['negative']) for r in rows],np.int32)
    assert not {block(r) for r in rows}&{block(r) for r in held}
    assert all(not near(a,b) for a in rows for b in held)
    scores=np.zeros(len(rows))
    for fold in folds:
        assert all(not near(rows[i],rows[j]) and block(rows[i])!=block(rows[j]) for i in fold['fit'] for j in fold['test'])
        scores[fold['test']]=predict(fit(x[fold['fit']],y[fold['fit']]),x[fold['test']])
    predictions=read(folder/'predictions.json')
    assert np.array_equal(scores,[r['score'] for r in predictions['development']])
    assert float(np.max(scores[y==0])+.025)==lock['threshold']
    gs=predict(cv2.ml.RTrees_load(str(folder/'model.xml')),gx)
    assert np.array_equal(gs,[r['score'] for r in predictions['guards']])
    assert np.array_equal(predict(fit(x,y),gx),gs)
    assert not lock['eligible'] and not (folder/'holdout-predictions.json').exists()
    result=dict(status='PASS',development_feature_replays=len(rows),guard_feature_replays=len(guards),
        real_target_counterfactuals=causal,spatial_model_refits=5,full_model_refit_and_reload='exact score match',
        spatial_buffers='verified across editions',held_out_48='not scored, viewed or labelled in this experiment',
        limitations='Exact same-environment replay; assistant visual references; no independent human audit or fresh-map evaluation')
    write(folder/'verification.json',result)
    print(folder.name+': features, target independence, spatial models and saved model replay PASS',flush=True)
    return result


def examples():
    rows={str(r['id']):r for r in read(BASE/'training.json')}
    cases=[('24365','1916 contour: usable explanation'),('88977','1924 contour: usable explanation'),
           ('72049','1924 contour: wrong curve location'),('32724','Text: some ink also follows contours'),
           ('11723','Vegetation: partial overlap'),('81041','Uncertain mark: explanation unavailable')]
    board=Image.new('RGB',(1040,1008),'white');draw=ImageDraw.Draw(board)
    details=[]
    for n,(identity,title) in enumerate(cases):
        row=rows[identity];x=(n%2)*520;y=(n//2)*336
        with Image.open(ROOT/row['context']) as source:im=source.convert('RGB')
        _,info,masks=f2.extract(im,row['context_box'],True)
        overlay=np.array(im);overlay[masks['skeleton']]=[45,105,230]
        overlay[masks['tube']]=(overlay[masks['tube']]*.4+np.array([80,225,120])*.6).astype(np.uint8)
        overlay[masks['residual']]=[220,40,60]
        overlay=Image.fromarray(overlay)
        for pic in (im,overlay):ImageDraw.Draw(pic).rectangle(row['context_box'],outline='#d07a00',width=1)
        board.paste(ImageOps.contain(im,(248,248),Image.Resampling.NEAREST),(x+8,y+52))
        board.paste(ImageOps.contain(overlay,(248,248),Image.Resampling.NEAREST),(x+264,y+52))
        draw.text((x+8,y+5),title,fill='black')
        draw.text((x+8,y+23),f"POI {identity} | explained ink {info['explained_ink_fraction']:.0%} | available {info['available']}",fill='black')
        draw.text((x+8,y+309),'Original context + target',fill='black')
        draw.text((x+264,y+309),'Predicted tube green; residual ink red',fill='black')
        details.append(dict(id=identity,title=title,label=row['label'],features=info))
    board.save(v2.OUT/'examples.png');write(v2.OUT/'example-index.json',details)


def report():
    examples();baseline=read(BASE/'development-summary.json')['appearance-structure']
    rows=read(BASE/'training.json');results={};table=''
    for name,folder in [('Baseline',BASE),('Curve traces',v1.OUT),('Continuous traces',v2.OUT)]:
        if name=='Baseline':s=baseline;edition=dict(JM50K_1924_new=dict(hits=2,contours=33));available='—'
        else:
            s=read(folder/'summary.json');edition=s['editions'];available=str(s['curve_available_contours'])+'/96'
            telemetry=read(folder/'feature-telemetry.json')['development']
            missing=Counter('insufficient reference paths' if r['features']['neighbor_count']<2 else 'inconsistent curvature' if r['features']['shape_deviation']>6 else 'missing paired anchors'
                for r,target in zip(telemetry,rows) if target['negative'] and not r['features']['available'])
            times=[r['feature_ms'] for r in telemetry]
            results[name]=dict(summary=s,unavailable_contour_reasons=dict(missing),
                feature_ms=dict(median=float(np.median(times)),p95=float(np.percentile(times,95)),maximum=max(times)))
        table+=f"<tr><td>{name}</td><td>{s['contour_hits']}/96</td><td>{edition['JM50K_1924_new']['hits']}/33</td><td>{s['protected_hits']}/122</td><td>{s['guard_hits']}/58</td><td>{available}</td></tr>"
    write(v2.OUT/'comparison.json',dict(baseline=baseline,candidates=results,decision='Reject both curve variants; preserve the untouched holdout and keep production unchanged'))
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Curve explanation experiment</title>
<style>body{{max-width:1120px;margin:24px auto;padding:0 18px;font:17px/1.6 system-ui;background:#fafaf5;color:#203b32}}a{{color:#24684d}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;min-width:740px}}td,th{{padding:12px;border-bottom:1px solid #ccd4c8;text-align:left}}.scroll{{overflow:auto}}.notice{{padding:18px;background:#edf0df}}</style>
<a href="/">Back to map</a> · <a href="../contour-learner/report.html">Previous learned model</a><h1>Predicting curves across a hidden target did not improve this classifier</h1><p>3 October 2026 · Completed paired experiments and verification; no production changes.</p>
<p class="notice">Both implementations failed the fixed development criteria. The baseline catches <strong>16/96 contours</strong>; adding curve-residual measurements catches <strong>7/96</strong>, or <strong>5/96</strong> with a tracer that crosses short print breaks. Results on 1924 contours fell from <strong>2/33 to 1/33 and 0/33</strong>. Neither candidate was advanced to the 48-target holdout.</p>
<h2>Same images, labels, folds, forest settings and calibration rule</h2><div class="scroll"><table><tr><th>Variant</th><th>Contour hits</th><th>1924 hits</th><th>Calibrated protected flags</th><th>Reused protection flags</th><th>Usable curve prediction</th></tr>{table}</table></div>
<p>The cutoff remains the largest protected spatial out-of-fold score plus 0.025. Zero flags on those 122 examples is therefore a calibration property, not independent safety evidence. All 58 separate reused protection probes also remain unflagged. Tree votes are not calibrated probabilities. Models are compared with the same fixed seed; these outcomes do not establish that curve information is inherently harmful across all models or seeds.</p>
<h2>What was implemented</h2><p>The target and a four-pixel halo are erased before estimating any background curves. The estimator traces outside skeleton paths, fits neighboring local quadratic curves and requires matching contour anchors on both sides of the target. It predicts narrow contour bands through the hidden region. The target is then revealed to measure unexplained strokes, connected fragments and loops; 14 measurements are appended to the existing model.</p>
<p>The first version stops at branches. It lacked enough reference paths for 68/96 contours. A second, separately frozen version follows the smoothest continuation at junctions and can bridge gaps of at most three pixels. Its direction check is used when choosing a branch or bridging a gap; unique ordinary raster stair-steps continue without that check. This avoids mistaking a one-pixel step for a sharp geometric bend. All other fit, anchor and model settings remain fixed.</p>
<p>The second version reduced insufficient-reference failures to 60/96, but eight more contours had inconsistent neighbor shapes and six lacked paired anchors. Its prediction was available for only 22/96 contours; some available curves still missed the actual target ink. Better path availability did not translate into better discrimination at the protected cutoff.</p>
<h2>Visual evidence</h2><a href="examples.png"><img src="examples.png" alt="Successful and failed contour predictions and partial overlap with text and vegetation"></a>
<p>Orange boxes mark targets. Blue pixels show the outside skeleton, not necessarily the selected reference paths. Green shows the independently predicted contour band inside the target; red shows unexplained target ink. These are v2 feature explanations, not classifier decisions. A useful-looking curve fit must not be confused with a validated noise label. <a href="example-index.json">Exact example telemetry</a>.</p>
<h2>Checks completed</h2><p>Seven synthetic regression cases cover target independence, curved contour explanation, a crossing stroke remaining visible, isolated symbols, blank images, small versus large breaks, and continuation through a T-junction. Both feature implementations replay exactly on all 218 training and 58 protection crops. In each implementation, overwriting the target with black pixels on every one of the 218 real training crops left the inferred background curves exactly unchanged.</p>
<p>Each candidate also passed exact replay of its five geographically buffered fold models, a full refit and saved-model reload. Source/input/model hashes and cross-edition geographic buffers passed. The 48 held-out images remain unscored and unlabelled in this experiment. Verification is on the same host and libraries, with assistant visual references; it is not independent human or new-map validation.</p>
<p>Feature-only median/p95 time was {results['Curve traces']['feature_ms']['median']:.1f}/{results['Curve traces']['feature_ms']['p95']:.1f} ms for v1 and {results['Continuous traces']['feature_ms']['median']:.1f}/{results['Continuous traces']['feature_ms']['p95']:.1f} ms for v2, excluding image decoding, disk I/O, baseline features and model inference. No production latency claim is made.</p>
<h2>Decision</h2><p><strong>Reject both variants.</strong> The target-isolation mechanism is verified, but this local curve-family approximation does not explain enough real map marks reliably. Keep the prior classifier as the research baseline; automatic suppression remains disabled. The hypothesis was tested through implementation, comparison, failure diagnosis, one targeted correction, replay and reporting. There is no pending deployment step for these rejected models.</p>
<p><a href="comparison.json">Full comparison and timing</a> · <a href="contract.json">v2 contract</a> · <a href="verification.json">v2 verification</a> · <a href="../contour-curves/verification.json">v1 verification</a> · <a href="predictions.json">v2 scores</a> · <a href="../contour-curves/predictions.json">v1 scores</a></p></html>'''
    (v2.OUT/'report.html').write_text(page,encoding='utf8')
    (v1.OUT/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Contour curve trial</title><h1>Contour curve trial</h1><p>Original curve features: 7/96 contour hits. Baseline: 16/96.</p><a href="../contour-curves-v2/report.html">Full comparison, corrected tracing variant and verification</a></html>',encoding='utf8')
    for trial,feature in [(v1,f1),(v2,f2)]:
        paths=[p for p in trial.OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json']
        paths += [ROOT/'tools/report_contour_curves.py',ROOT/'tests/test_contour_curve_features.py',
                  ROOT/'tools/contour_learner_trial.py',ROOT/'tools/contour_topology_trial.py',
                  ROOT/'tools/contour_frequency_trial.py',ROOT/'tools/contour_learner_data.py']
        paths += [ROOT/feature.__file__,ROOT/trial.__file__]
        write(trial.OUT/'artifact-manifest.json',{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
    print('Comparison, examples and frozen manifests written.',flush=True)


if __name__=='__main__':
    verify(v1,f1);verify(v2,f2);report()
