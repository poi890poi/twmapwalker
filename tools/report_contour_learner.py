"""Independent replay and a readable report for the frozen learned classifier trial."""
import math
from collections import Counter

import cv2
import numpy as np

from .contour_learner_data import ROOT,OUT,sha,read,write,block,near,sheets
from .contour_learner_trial import all_features,fit,predict,PARAMS


def verify():
    lock=read(OUT/'model-lock.json')
    for key,path in [('code_sha256',ROOT/'tools/contour_learner_trial.py'),('training_sha256',OUT/'training.json'),
                     ('features_sha256',OUT/'features.npz'),('holdout_sha256',OUT/'holdout-inputs.json'),
                     ('parameters_sha256',OUT/'parameters.json'),('labels_sha256',OUT/'new-protection-labels.json')]:
        assert sha(path)==lock[key],path
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');held=read(OUT/'holdout-inputs.json')
    folds=read(OUT/'folds.json');saved=read(OUT/'development-predictions.json')
    x,_=all_features(rows);gx,_=all_features(guards)
    for file,arrays in [('features.npz',x),('guard-features.npz',gx)]:
        frozen=np.load(OUT/file)
        for method in PARAMS['methods']:assert np.array_equal(frozen[method],arrays[method])
    assert len({str(r['id']) for r in rows+held})==len(rows)+len(held)
    assert not {block(r) for r in rows}&{block(r) for r in held}
    for a in rows:
        assert not any(near(a,b) for b in held)
    assert sorted(i for fold in folds for i in fold['test'])==list(range(len(rows)))
    for fold in folds:
        for i in fold['fit']:
            assert not any(near(rows[i],rows[j]) or block(rows[i])==block(rows[j]) for j in fold['test'])
    y=np.array([int(r['negative']) for r in rows],dtype=np.int32)
    for method in PARAMS['methods']:
        actual=np.zeros(len(rows))
        for f in folds:
            actual[f['test']]=predict(fit(x[method][f['fit']],y[f['fit']]),x[method][f['test']])
        assert np.array_equal(actual,np.array([r['score'] for r in saved[method]['oof']]))
        cutoff=max(actual[y==0])+.025
        assert cutoff==lock['models'][method]['threshold']
        assert np.array_equal(actual>cutoff,[r['reject'] for r in saved[method]['oof']])
        path=OUT/f'{method}.xml';assert sha(path)==lock['models'][method]['model_sha256']
        loaded=cv2.ml.RTrees_load(str(path));gs=predict(loaded,gx[method])
        assert np.array_equal(gs,[r['score'] for r in saved[method]['guards']])
        retrained=fit(x[method],y)
        assert np.array_equal(predict(retrained,gx[method]),gs)
        print(f'{method}: exact replay of five folds, final refit and saved-model reload PASS',flush=True)
    # Hash holdout crops without extracting features or displaying their pixels.
    for r in held:assert sha(ROOT/r['context'])==r['context_sha256']
    assert not (OUT/'holdout-predictions.json').exists()
    result=dict(status='PASS',training_rows=len(rows),guard_rows=len(guards),held_out_rows_preserved=len(held),
        checks=['All image, source and model lock hashes match',
            'Exact feature replay for 218 training and 58 protection crops',
            'Five spatial OOF models per feature set reproduce all saved scores',
            'Full refit and saved XML reload reproduce protection predictions',
            'No shared geographic blocks or two-tile neighborhoods between fit and test, including cross-edition copies',
            'Holdout identities and hashes verified without consuming pixels or labels'],
        independent_limits='Same host and library versions; no independent human review or new edition validation.')
    write(OUT/'verification.json',result)
    return result


def report():
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');summary=read(OUT/'development-summary.json')
    preds=read(OUT/'development-predictions.json');labels=read(OUT/'new-protection-labels.json')
    byid={str(r['id']):r for r in rows}
    breakdown={}
    for method,results in preds.items():
        breakdown[method]={}
        for source in sorted({r['source'] for r in rows}):
            negatives={str(r['id']) for r in rows if r['negative'] and r['source']==source}
            hits=sum(str(r['id']) in negatives and r['reject'] for r in results['oof'])
            breakdown[method][source]=dict(contours=len(negatives),hits=hits)
    write(OUT/'edition-breakdown.json',breakdown)
    selected=['33104','65352','70289','72049','51096','81041']
    newrows=read(OUT/'new-protection-inputs.json')
    selected += [str(r['id']) for r in newrows if r['index'] in [20,45,67,7,91]]
    cards=[byid[i].copy() for i in selected]
    control=next(r.copy() for r in guards if r['id']=='control-9');control['source']='hot spring control';cards.append(control)
    for i,r in enumerate(cards):r['index']=i+1
    sheets(cards,OUT,'diagnostic')
    write(OUT/'diagnostic-index.json',[dict(index=r['index'],id=r['id'],label=r['label'],role='contour hit' if i<4 else 'protected/uncertain') for i,r in enumerate(cards)])
    table=''
    for name,r in summary.items():
        table+=f"<tr><td>{name}</td><td>{r['contour_hits']}/{r['contours']} ({100*r['contour_hits']/r['contours']:.1f}%)</td><td>{r['protected_hits']}/{r['protected']}</td><td>{r['guard_hits']}/{r['guard_count']}</td><td>{r['threshold']:.5f}</td></tr>"
    timing=read(OUT/'timing.json')['feature_ms']
    write(OUT/'result.json',dict(decision='Keep both models offline; reject before held-out evaluation under the frozen minimum-gain rule',
        development=summary,edition_breakdown=breakdown,new_visual_labels={k:len(v) for k,v in labels.items() if isinstance(v,list)},
        feature_latency_ms=dict(median=float(np.median(timing)),p95=float(np.percentile(timing,95)),maximum=max(timing)),
        next_failure_to_address='High scoring uncertain target marks cap safe coverage. The structural addition also gives only 2/33 contour hits in the 1924 edition. Avoid lowering the threshold or relabelling ambiguous examples to manufacture gains.'))
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Learned contour classifier comparison</title>
<style>body{{max-width:1100px;margin:24px auto;padding:0 18px;background:#fafaf5;color:#203b32;font:17px/1.6 system-ui}}a{{color:#24684d}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;min-width:720px}}td,th{{padding:12px;border-bottom:1px solid #ccc;text-align:left}}.scroll{{overflow:auto}}.notice{{padding:18px;background:#edf0df}}</style>
<a href="/">Back to map</a> · <a href="../contour-topology/report.html">Earlier fixed-rule experiments</a><h1>Learning improves contour removal, but the gain is still too small</h1><p>3 October 2026 · Two trained classifiers, frozen settings, geographic separation.</p>
<p class="notice">Adding native size, frequency and line-structure features improved contour hits from <strong>10/96 to 16/96</strong>. Both models preserved all <strong>58 separate reused protection probes</strong>. Neither reached the <strong>25% removal target fixed before training</strong>, so both remain offline and the 48 held-out crops are preserved uninspected.</p>
<h2>Paired comparison</h2><div class="scroll"><table><tr><th>Model features</th><th>Contour hits</th><th>OOF protected flags</th><th>Separate probe flags</th><th>Vote cutoff</th></tr>{table}</table></div>
<p><strong>The zero out-of-fold (OOF) protected flags are a calibration result, not an independent safety result.</strong> Each threshold was selected above the largest score among the 122 protected or uncertain OOF examples, with a fixed 0.025 margin. The 58 old protection probes were excluded from fitting and threshold selection; they are reused regression examples and may share nearby map areas, not a fresh generalization set. Votes are model scores, not calibrated probabilities.</p>
<p>The structural model caught 14/63 contours in the 1916 edition and only 2/33 in the 1924 edition. All 16 hits came from the existing contour-negative collection; none came from the 10 additional contour patches found during the new OCR review. The gain therefore does not come from counting those newly discovered large patches.</p>
<h2>More real marks to protect</h2><p>Reviewed 96 new targets selected through OCR proposals: 38 number targets, 18 Chinese text targets, 4 Kana targets, 17 vegetation-like marks, 4 repeated symbols, 5 uncertain targets and 10 actual contour patches. OCR strings supplied selection strata only, never training labels or inference features. Some Kana had been misread as Chinese by OCR. All non-contour targets remain protected for this contour-only task.</p>
<p>After reserving geography, training contains 218 targets: 96 contours and 122 protected/uncertain marks. Old rare-symbol probes, including the hot spring control, remain outside training. New labels are assistant visual assessments of the red target box, not independently verified ground truth; surrounding pixels can contain unrelated real marks.</p>
<h2>Examples and limiting cases</h2><a href="diagnostic-0.jpg"><img src="diagnostic-0.jpg" alt="Four correctly caught contour fragments, two high-scoring uncertain marks, Kana, numbers and a hot spring protection control"></a>
<p>Examples 1–4: contours caught by the structural model. Examples 5–6: uncertain targets with the highest protected model scores; these determine the conservative cutoff. Examples 7–11: newly reviewed numbers and Kana. Example 12: the reused hot spring control. <a href="diagnostic-index.json">Exact example identities</a>.</p>
<h2>How the experiment avoids nearby-copy leakage</h2><p>Geographic 4×4 tile blocks are assigned consistently across the two map editions. Both models use the same five spatial folds. Every fold excludes the test blocks and a two-tile neighborhood around each test crop from its fitting set. A separate 48-target collection was frozen first; training excludes its blocks and two-tile neighborhoods. It has not been viewed, labelled or scored because neither candidate cleared the development gate.</p>
<p>These are new target crops within cached map areas, some previously visited by other studies. They should not be described as a new geographic domain or a new map edition. The frozen 48 targets comprise 24 symbol proposals, 12 number-read proposals and 12 name-read proposals; their actual visual labels are still unknown.</p>
<h2>Model, verification and limits</h2><p>Both models use 160 decision trees, maximum depth 8, minimum split sample count 3, fixed seed and class balancing. Baseline inputs are target/context image-gradient descriptors and local ink summaries. The second model adds 18 native-size, frequency and topology measurements. No geographic coordinates, edition identifiers, OCR strings, annotation status or semantic labels enter inference.</p>
<p>Exact replay verified all features, all five folds for each variant, full-model refits and saved-model reloads. Image hashes, source/model locks and spatial buffers passed. Feature extraction median {np.median(timing):.1f} ms, p95 {np.percentile(timing,95):.1f} ms on this host, excluding image decoding and I/O; both feature sets are computed together. This is not an end-to-end production latency measurement.</p>
<p><strong>Decision:</strong> preserve the trained models and their negative result; do not enable automatic hiding. Lowering the cutoff would sacrifice the explicit protection of ambiguous targets. The next improvement needs evidence that it distinguishes target ink from contour background more reliably, particularly in 1924 maps. This trial does not prove that more training data alone will solve that problem.</p>
<p><a href="contract.json">Predeclared contract</a> · <a href="training.json">Training manifest</a> · <a href="development-predictions.json">All predictions</a> · <a href="result.json">Results and timings</a> · <a href="verification.json">Verification</a> · <a href="model-lock.json">Frozen models and thresholds</a></p>
<h2>New protection-set contact sheets</h2>'''+''.join(f'<a href="protection-{i}.jpg"><img loading="lazy" src="protection-{i}.jpg" alt="New protection review sheet {i+1}"></a>' for i in range(8))+'</html>'
    (OUT/'report.html').write_text(page,encoding='utf8')
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json']
    paths += [ROOT/'tools'/name for name in ['contour_learner_data.py','contour_learner_trial.py','report_contour_learner.py',
                                            'contour_frequency_trial.py','contour_topology_trial.py']]
    write(OUT/'artifact-manifest.json',{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)})
    print('Report and manifest written. Models remain offline; holdout remains unconsumed.',flush=True)


if __name__=='__main__':
    verify();report()
