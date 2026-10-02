"""Score frozen predictions and publish a reviewable noise-verifier decision."""
import html
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import noise_verifier_trial as t

OUT=t.OUT


def counts(samples):
    result={}
    for label in sorted({r['label'] for r in samples}):
        rr=[r for r in samples if r['label']==label]
        result[label]=dict(findings=len(rr),physical_groups=len({r['physical_group'] for r in rr}),
                           rejected=sum(r['reject'] for r in rr),guarded_rejected=sum(r['guarded_reject'] for r in rr),
                           guarded_rejected_groups=len({r['physical_group'] for r in rr if r['guarded_reject']}))
    return result


def main():
    rows=t.read(OUT/'dataset.json'); fresh=t.read(OUT/'fresh/dataset.json')
    refs=t.read(OUT/'fresh/visual-labels.json')['labels']; newer=t.read(OUT/'new-visual-labels.json')['labels']
    results={**t.read(OUT/'evaluation.json'),**t.read(OUT/'craft/evaluation.json')}
    predictions=t.read(OUT/'fresh/predictions.json'); scored={}
    for method,rr in predictions.items():
        lookup={str(r['id']):r for r in fresh}
        scored[method]=[dict(**r,label=refs[str(r['id'])],physical_group=lookup[str(r['id'])]['physical_group'],source=lookup[str(r['id'])]['source']) for r in rr]
    summary=dict(new_spatial={m:counts([r for r in v['samples'] if r['split']=='new-spatial']) for m,v in results.items()},
                 fresh={m:counts(rr) for m,rr in scored.items()},
                 controls={m:counts([r for r in v['samples'] if r['split']=='regression-control']) for m,v in results.items()})
    t.write('summary.json',summary)
    # Independent replay verifies saved numbers; labels do not participate in inference.
    checks=[]
    for method,folder,feature_name in [('hog-mark',OUT,'features.npz'),('craft-mark',OUT/'craft','craft-features.npz')]:
        lock=t.read(folder/'locked-model.json'); arrays=np.load(folder/'features.npz'); ids=np.array(lock['fit_indices'])
        model=t.train(arrays[method][ids],np.array(lock['fit_labels']))
        score,ratio=t.predict(model,np.load(OUT/'fresh'/feature_name)[method])
        saved=predictions[method]
        assert np.allclose(score,[r['score'] for r in saved],rtol=0,atol=1e-5)
        assert np.allclose(ratio,[r['ratio'] for r in saved],rtol=0,atol=1e-5)
        checks.append(method+' fresh prediction replay agrees within 1e-5')
    for r in rows:
        assert t.digest(OUT/r['crop'])==r['sha256']
    for r in fresh:
        assert t.digest(OUT/'fresh'/r['crop'])==r['sha256']
        assert all(not t.near(r,a,2) for a in rows if 'source' in a)
    assert len({r['block'] for r in fresh})==len(fresh)==48
    assert set(refs)=={str(r['id']) for r in fresh}
    changes=[]
    current={r['id']:r for r in t.read(OUT/'label-audit.json')['current']}
    for r in rows:
        if r['id'] in current and r['classification']!=current[r['id']]['classification']: changes.append(r['id'])
    assert not changes
    t.write('verification.json',dict(checks=checks+['All 204 crop hashes match','All 48 fresh candidates occupy separate 4x4 blocks and avoid two-tile neighborhoods of development/new annotation areas','All fresh candidates have visual labels','Old user classifications agree with current annotations'],note='No application behavior changed. No production regression suite necessary for offline-only harness. Spatial samples and assistant morphology labels do not establish whole-map safety.'))
    # Review failures and the safe method's actual hits, using native pixels.
    examples=[('Hot-spring mark wrongly rejected',OUT,rows,'control-9'),
              ('Vegetation-like: guarded HOG hit',OUT,rows,38819),
              ('Fresh vegetation-like: guarded HOG hit',OUT/'fresh',fresh,99624),
              ('Fresh ambiguous mark: guard abstains',OUT/'fresh',fresh,33495)]
    board=Image.new('RGB',(1000,330),'white'); draw=ImageDraw.Draw(board)
    for i,(title,folder,items,key) in enumerate(examples):
        r=next(r for r in items if r['id']==key); im=Image.open(folder/r['crop']).convert('RGB')
        ImageDraw.Draw(im).rectangle(r['crop_box'],outline='red',width=1)
        im.thumbnail((235,260)); scale=min(235/im.width,260/im.height);im=im.resize((round(im.width*scale),round(im.height*scale)))
        board.paste(im,(i*250,60)); draw.text((i*250+5,5),title.replace(': ',':\n').replace(' wrongly','\nwrongly'),fill='black');draw.text((i*250+5,40),str(key),fill='black')
    board.save(OUT/'decision-examples.jpg')
    table=[]
    for method,v in results.items():
        rr=[r for r in v['samples'] if r['split']=='new-spatial']
        noise=[r for r in rr if r['label']=='noise']; veg=[r for r in rr if r['label']=='vegetation-like']; protect=[r for r in rr if r['target']==-1]
        controls=[r for r in v['samples'] if r['split']=='regression-control']
        table.append(f"<tr><td>{method}</td><td>{sum(r['guarded_reject'] for r in noise)}/{len(noise)}</td><td>{sum(r['guarded_reject'] for r in veg)}/{len(veg)}</td><td>{sum(r['guarded_reject'] for r in protect)}/{len(protect)}</td><td>{sum(r['guarded_reject'] for r in controls)}/{len(controls)}</td></tr>")
    timings=t.read(OUT/'feature-timing.json'); craft=t.read(OUT/'craft-feature-timing.json')
    decision='''# Decision: establish separate noise classes; do not deploy suppression yet

The guarded HOG mark verifier is retained for research only: it rejected one of
13 newer vegetation-like findings and one of eight fresh vegetation-like findings,
with no observed protected losses in these samples. It did not reject any of the
ten newer user-noise findings or eleven fresh contour-only findings. CRAFT mark
features did not reproduce their one newer vegetation hit on the fresh sample.
Context HOG has no useful held-out gain. Context CRAFT rejects more noise but also
the known hot-spring symbol; reject that candidate without testing it further.

The guard matters: unguarded HOG rejected an ambiguous tiny mark on the fresh
1924 sample. It must abstain there. Ambiguous samples must not be relabeled noise
just to improve precision. Positive control results include small Kana, Chinese
glyphs, 651, school 文 and hot spring. The old ten controls were not used to fit
or calibrate the methods; they are reused regression references, not fresh proof.

## What the next model needs

1. Multi-class targets: contour fragments, repeated vegetation, marginal print,
   text (including Kana and numerals), discrete landmark symbols, and unknown.
   Keep the original user annotation alongside visual subtype/provenance. Other
   supplies candidates for review, not an automatic negative label.
2. Rare-symbol positive training examples, including hot springs, school symbols,
   survey/spot-height marks, and isolated Kana strokes. The current development
   corpus lacks such breadth: being unlike ordinary text is not evidence of noise.
   Use separate held-out examples of each type; training on the control and then
   claiming the same control is preserved would be circular.
3. Train a crop-and-context classifier on real patches with class-specific hard
   negatives and positive controls. Preserve aspect ratio and add scale/rotation/
   ink degradation augmentation as separately tested changes. A shared CRAFT
   feature map can reduce eventual inference overhead, but the current fixed
   encoder/context experiment is not safe enough to deploy.
4. Require class agreement and an explicit unknown/abstain path. Missing OCR,
   missing OSM matches, ring shape alone, or repetition alone must not hide a
   candidate. Semantic sheet-margin exclusion needs sheet-boundary evidence;
   a text classifier cannot determine that printed words are marginalia.
5. Expand and spatially hold out a protection set before changing the detector.
   With zero errors, about 598 genuinely independent positive examples would be
   needed merely to put a one-sided 95% binomial upper bound below 0.5% loss.
   This is a sample-size guide, not a claim that correlated map crops are independent.
   Include both map editions, rare symbols, numbers and small Kana explicitly.

First integration, only after a useful method passes these gates: add reversible
noise suggestions with reasons and original crops. Evaluate downstream grouping
on those suggestions. Automatic hiding requires stronger evidence; nothing in
this round changes production detection, annotation visibility, OCR or grouping.
'''
    (OUT/'decision.md').write_text(decision,'utf-8')
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Noise verification — Mapwalker</title>
<style>body{{font:17px/1.55 system-ui,sans-serif;color:#173d36;background:#f5f3e9;max-width:1100px;margin:auto;padding:24px}}section{{background:white;border-radius:14px;padding:22px;margin:24px 0}}h1,h2{{line-height:1.2}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border-bottom:1px solid #ccd;text-align:left}}.scroll{{overflow:auto}}img{{max-width:100%;height:auto}}a{{color:#006b75}}.note{{border-left:5px solid #a96022;padding-left:18px}}</style>
<a href="/">← Mapwalker</a><h1>Noise first: test a separate verifier</h1>
<p class="note"><b>No production filtering enabled.</b> A conservative crop verifier catches a small amount of vegetation noise. The stronger context model also rejects a real hot-spring symbol and is rejected.</p>
<section><h2>What the pixels show</h2><img src="decision-examples.jpg" alt="Four examples: rejected hot spring, two vegetation hits, and an ambiguous tiny mark preserved by the guard"><p>Red rectangles are the original automatic candidate boxes. The surrounding map is part of the evidence.</p></section>
<section><h2>Same labels, different image representations</h2><p>Fit on 103 old findings, reduced to 98 physical groups. Calibrate with held-out 4×4 tile blocks plus one-tile buffers. Then test on 42 newer findings away from those areas: 10 user-noise, 13 vegetation-like Other, 13 POI, and six uncertain Other. Only the old development labels enter fitting or calibration.</p>
<div class="scroll"><table><tr><th>Guarded method</th><th>Noise rejected</th><th>Vegetation rejected</th><th>Protected lost</th><th>Old controls lost</th></tr>
<tr><td>Retain-all baseline</td><td>0/10</td><td>0/13</td><td>0/19</td><td>0/10</td></tr>{''.join(table)}</table></div>
<p>HOG describes image gradients. CRAFT supplies learned image features from the existing frozen text encoder. Each comparison uses the same class-balanced kernel classifier and conservative calibration rule. “Context” adds surrounding pixels. The guard requires a substantially nearer negative exemplar than protected exemplar. Scores are not probabilities.</p>
<p>The newer 42 findings represent {len({r['physical_group'] for r in rows if r['split']=='new-spatial'})} physical groups. Table counts are findings; <a href="summary.json">the summary also reports physical groups</a>. Only HOG was proposed before these images were inspected; learned-feature results on this set are reused diagnostics.</p></section>
<section><h2>Fresh sample after locking the methods</h2><p>48 candidates from 48 distinct 4×4 tile blocks, evenly sampled across two map editions and three detector/read-status families. Two-tile neighborhoods around training and newer annotation areas were excluded. Only the surviving mark-based methods were run.</p>
<ul><li><b>Guarded HOG:</b> 1/8 vegetation-like marks rejected; 0/11 contour-only noise rejected; 0/29 text, numeric or uncertain marks lost.</li><li><b>Without its guard:</b> HOG additionally rejects one ambiguous tiny mark. That is counted as a failure, not reclassified as noise.</li><li><b>CRAFT mark:</b> rejects nothing on this fresh sample.</li></ul>
<p>The 29 protected cases comprise eight recognizable text regions, nine numerals and 12 uncertain marks. Labels are assistant visual assessments, made before inspecting saved predictions; they are not independent human ground truth. Sampling detected candidates cannot measure missed-POI recall.</p>
<p><a href="fresh/input-fresh-spatial-0.jpg">Fresh sheet 1</a> · <a href="fresh/input-fresh-spatial-1.jpg">Fresh sheet 2</a> · <a href="fresh/visual-labels.json">Labels and provenance</a></p></section>
<section><h2>Decision and next method</h2><p>Retain the guarded crop verifier as a research baseline. Reject the context CRAFT candidate. Noise removal is not solved: the small safe gain is concentrated in vegetation, and the models do not handle rare landmark symbols reliably.</p>
<p>The next model needs separate contour, vegetation, marginal-print, text, landmark-symbol and unknown classes, with real hard negatives and rare-symbol positive training examples. Keep numerals and ambiguous marks protected. Test each class on separate map areas; allow the verifier to abstain. “Other” and “no OCR/OSM match” must not become automatic noise labels.</p>
<p><a href="decision.md">Detailed decision and acceptance gates</a>. No application code, stored annotations or detector weights changed.</p></section>
<section><h2>Costs and reproducibility</h2><p>Feature extraction for both HOG variants: mean {timings['mean']:.2f} ms, median {timings['median']:.2f}, p95 {timings['p95']:.2f}, maximum {timings['maximum']:.2f} per crop. Both CRAFT variants on {html.escape(craft['device'])}: mean {craft['mean']:.2f} ms, median {craft['median']:.2f}, p95 {craft['p95']:.2f}, maximum {craft['maximum']:.2f}; model initialization {craft['init_ms']:.0f} ms. Excludes PNG decoding and disk I/O; classifier fit/prediction timings are separate in the raw outputs. Offline timings do not establish production throughput.</p>
<p><a href="contract.md">Contract</a> · <a href="dataset.json">Frozen data</a> · <a href="development.json">HOG calibration</a> · <a href="craft/development.json">Learned-feature calibration</a> · <a href="evaluation.json">HOG predictions</a> · <a href="craft/evaluation.json">Learned predictions</a> · <a href="fresh/predictions.json">Fresh predictions</a> · <a href="verification.json">Verification</a> · <a href="artifact-manifest.json">Hashes</a></p></section></html>'''
    (OUT/'report.html').write_text(page,'utf-8')
    # Include external source scripts and reference dependencies in the manifest.
    paths=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact-manifest.json')
    paths += [t.ROOT/'tools'/n for n in ['noise_verifier_trial.py','noise_craft_features.py','noise_fresh_holdout.py','run_noise_craft_trial.py','report_noise_verifier.py','probe_hollow_dots.py']]
    t.write('artifact-manifest.json',[dict(path=str(p.relative_to(t.ROOT)),sha256=t.digest(p),bytes=p.stat().st_size) for p in paths])
    print(json.dumps(summary['fresh'],indent=2))


if __name__=='__main__': main()
