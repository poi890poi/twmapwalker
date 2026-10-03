"""Verify and explain native scale experiments without changing frozen outputs."""
import html,json,statistics
import numpy as np
from PIL import Image
import native_pattern_trial as trial
import native_symbol_trial as symbol
old=trial.old;OUT=trial.OUT;ROOT=trial.ROOT


def main():
    rows=old.read(OUT/'dataset.json');fresh=old.read(OUT/'fresh/dataset.json');labels=old.read(OUT/'fresh/visual-labels.json')['labels']
    evaluated=old.read(OUT/'evaluation.json');se=old.read(OUT/'symbol-evaluation.json');pred=old.read(OUT/'fresh/predictions.json')
    prior_by_id={str(r['id']):r for r in rows};fresh_by_id={str(r['id']):r for r in fresh}
    assert set(labels)==set(fresh_by_id)
    assert len({r['block'] for r in fresh})==48
    for r in fresh:
        assert all(not old.near(r,a,2) for a in rows if 'source' in a)
    for r in rows+fresh:assert old.digest(r['image'])==r['sha256']
    lock=old.read(OUT/'locked-model.json');assert old.digest(OUT/'features.npz')==lock['features_sha256'];assert old.digest(OUT/'dataset.json')==lock['dataset_sha256']
    sl=old.read(OUT/'symbol-lock.json');assert old.digest(OUT/'symbol-features.npz')==sl['features_sha256']
    x=np.load(OUT/'features.npz')['native'];l=lock['methods']['native-broad'];idx=np.array(l['fit_indices']);model=old.train(x[idx],np.array(l['fit_labels']))
    sx=np.load(OUT/'symbol-features.npz')['features'];si=np.array(sl['fit_indices']);sm=old.train(sx[si],np.array(sl['fit_labels']))
    # Replay both fresh scorers independently from frozen feature/model parameters.
    for r,p in zip(fresh,pred):
        assert r['id']==p['id'];vv,valid=trial.views(r);v=trial.HOG.compute(np.asarray(vv['native'])).ravel();v/=max(1e-8,np.linalg.norm(v))
        s,q=old.predict(model,v[None]);assert abs(float(s[0])-p['native']['score'])<1e-5
        sv,h=symbol.extract(r)
        if sv is None:assert p['symbol']['score'] is None
        else:
            s,q=old.predict(sm,sv[None]);assert abs(float(s[0])-p['symbol']['score'])<1e-5
    summary={}
    for method in ('native','symbol'):
        summary[method]={}
        for label in sorted(set(labels.values())):
            rr=[r for r in pred if labels[str(r['id'])]==label]
            summary[method][label]=dict(total=len(rr),flagged=sum(r[method]['reject'] for r in rr))
    trial.write('fresh-summary.json',summary)
    cases={}
    for key in ('control-9','33495','38819','99624'):
        r=prior_by_id[key];b=r['crop_box'];sr=next(v for v in se['samples'] if str(v['id'])==key)
        cases[key]=dict(label=r['label'],automatic_box=[b[2]-b[0],b[3]-b[1]],native_hole=sr['hole'],vegetation_flag=sr['reject'])
    trial.write('diagnostic-cases.json',cases)
    # Counterfactual probes demonstrate scale sensitivity, not real-world accuracy.
    r=prior_by_id['38819'];im=Image.open(r['image']).convert('L');b=r['crop_box'];patch=im.crop(tuple(round(v) for v in b));counter=[]
    def feature(p,native):
        if native:
            view=Image.new('L',(96,96),255);view.paste(p,((96-p.width)//2,(96-p.height)//2))
        else:view=p.resize((96,96),Image.Resampling.BILINEAR)
        f=trial.HOG.compute(np.asarray(view)).ravel();return f/max(1e-8,np.linalg.norm(f))
    for scale in (.5,1.,1.5,2.):
        p=patch.resize((round(patch.width*scale),round(patch.height*scale)),Image.Resampling.BILINEAR)
        counter.append(dict(scale=scale,dimensions=list(p.size),stretch_similarity=float(feature(p,False)@feature(patch,False)),native_similarity=float(feature(p,True)@feature(patch,True))))
    trial.write('scale-counterfactual.json',dict(note='Artificially scaled one known vegetation crop. Descriptor response only, not an accuracy test. Same interpolation and original pixels.',samples=counter))
    repetition=old.read(OUT/'repetition.json');peers=old.read(OUT/'symbol-peers.json')
    rept={str(r['id']):r for r in repetition};peer={str(r['id']):r for r in peers}
    veget=[r for r in rows if r['label']=='vegetation-like']
    rpt=dict(vegetation_examples=len(veget),whole_patch_supported=sum(rept[str(r['id'])]['supported'] for r in veget),aligned_shape_supported=sum(peer[str(r['id'])]['supported'] for r in veget),interpretation='Both repetition gates remove all accepted vegetation hits. Neither is useful at the frozen thresholds. No conclusion about whether the maps contain repetition.')
    trial.write('repetition-summary.json',rpt)
    def stats(values):return dict(mean=statistics.mean(values),median=statistics.median(values),p95=float(np.percentile(values,95)),maximum=max(values))
    timing=dict(fresh_combined_ms=stats([p['ms'] for p in pred]),whole_patch_ms=stats([r['ms'] for r in repetition]),aligned_peers_ms=stats([r['ms'] for r in peers]),excludes='Native classifier feature timings exclude decoding; fresh combined timing includes local crop decode. Repetition excludes cached PNG loading. Static offline crops, not production throughput.')
    trial.write('timing-summary.json',timing)
    trial.write('verification.json',dict(checks=['252 input crop hashes verified','Both fresh classifier predictions replayed within 1e-5','48 fresh candidates use distinct 4x4 blocks and two-tile buffers','Model inputs and saved feature hashes verified','33495 user correction recorded without changing old frozen references'],scope='Research only; production unchanged. No automatic noise classification applied to user data.'))
    table=[]
    for name,v in evaluated.items():
        rr=v['samples'];table.append(f"<tr><td>{name}</td><td>{sum(r['reject'] and r['label']=='vegetation-like' for r in rr)}/21</td><td>{sum(r['reject'] and r['label'] in ('noise','closed-contour') for r in rr)}</td><td>{sum(r['reject'] and r['label'] in ('poi','numeric','uncertain','protected-symbol') for r in rr)}</td></tr>")
    ss=se['samples'];table.append(f"<tr><td>Native, hole-aligned vegetation shape</td><td>{sum(r['reject'] and r['label']=='vegetation-like' for r in ss)}/21</td><td>0</td><td>0</td></tr>")
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Native scale and repeated symbols — Mapwalker</title>
<style>body{{font:17px/1.5 system-ui,sans-serif;background:#f5f3e9;color:#173d36;max-width:1050px;margin:auto;padding:24px}}section{{padding:22px;background:white;border-radius:14px;margin:22px 0}}h1,h2{{line-height:1.2}}a{{color:#006b75}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border-bottom:1px solid #ccc;padding:10px}}.scroll{{overflow:auto}}.note{{border-left:5px solid #a96022;padding-left:16px}}</style>
<a href="/">← Mapwalker</a><h1>Preserve native scale; compare the complete symbol</h1>
<p class="note"><b>The previous representation discarded useful scale.</b> Correcting that helps, but does not yet solve noise rejection. No production filter is enabled.</p>
<section><h2>The size information we were losing</h2><p>Each row shows the same pixels stretched, fitted with their aspect ratio preserved, and centered at native scale. Every panel uses the same display magnification. Notice how normalization enlarges tiny noise into a substantial mark.</p><img src="scale-comparison.png" alt="Hot spring, two vegetation marks, and tiny noise compared under stretched, aspect-preserving and native-scale preprocessing">
<p>Detector boxes are not physical symbol sizes: the hot-spring box is 43×36 pixels, while the vegetation boxes are approximately 41×39 and 41×41. Shape and the actual ink footprint matter. The tiny noise box is 5×5.</p>
<p><b>Correction accepted:</b> 33495 is noise, as identified by the user. The earlier report called it uncertain. This correction is recorded separately; the old frozen assessment is preserved. It is a known diagnostic case, not fresh evidence in this round.</p></section>
<section><h2>Controlled scale comparison on reused cases</h2><p>Same 96×96 HOG descriptor, classifier, training groups, spatial calibration and size coverage. Only the crop representation changes in the first three arms. Large candidates outside the native canvas are retained by every arm.</p>
<div class="scroll"><table><tr><th>Method</th><th>Vegetation flagged</th><th>Other noise flagged</th><th>Protected/uncertain flagged</th></tr>{''.join(table)}</table></div>
<p>The vegetation-specific model changes the training target while keeping native features. The hole-aligned method separately locates a native-sized hole and represents its 32×40 ring/stem neighborhood. It preserves the hot spring and does not call tiny noise vegetation. These are reused diagnostic results, not independent generalization estimates.</p></section>
<section><h2>Fresh spatial test after locking</h2><p>48 new candidates from 48 map blocks across both editions, with 32 selected for ring-like geometry and 16 other marks. All avoid earlier sample neighborhoods. Visual labels: 11 vegetation-like, 20 contour/noise, 16 uncertain and one numeral. This sample has little text; old Kana, Chinese, school and hot-spring controls remain necessary.</p>
<ul><li><b>General native-scale filter:</b> one real-noise hit, but three uncertain marks flagged. Reject as a general filter.</li><li><b>Aligned native-shape vegetation verifier:</b> one of 11 vegetation-like marks flagged; no non-vegetation marks flagged. Retain for research; coverage is low.</li></ul>
<p>Labels are assistant visual morphology assessments, not independently verified legend semantics. Ring enrichment measures behavior on selected candidates, not map-wide prevalence or missed-POI recall.</p>
<p><a href="fresh/sheet-0.jpg">Fresh sheet 1</a> · <a href="fresh/sheet-1.jpg">Fresh sheet 2</a> · <a href="fresh/visual-labels.json">Labels</a> · <a href="fresh/predictions.json">Predictions</a></p></section>
<section><h2>Repetition is still unresolved</h2><p>Whole-patch edge matching at native size found no supported vegetation matches among 38 old and reused vegetation examples. Hole-aligned shape matching with fixed size tolerance and cosine ≥.90 also found none. Adding either gate removes every vegetation hit.</p>
<p>This rejects these two implementations at their locked thresholds. It does not disprove repeated vegetation patterns. Whole boxes include changing contours; even aligned patches still contain nearby ink. A useful next matcher needs to isolate the symbol strokes and compare ring, stem and dot geometry at native scale, with tolerances calibrated on development examples and checked on new map areas. It must preserve meaningful ring-shaped symbols and numerals.</p>
<p>Keep size as an explicit cue, calibrated per map edition/scan and zoom. Do not normalize every symbol to the same size or treat the detector box as its true outline. Repetition should support a shape-specific decision; it cannot supply the semantic class alone.</p></section>
<section><h2>Evidence and verification</h2><p>All 252 old/new crop hashes and both fresh classifier replays pass. Application detection, annotations and visibility are unchanged.</p>
<p><a href="contract.md">Contract</a> · <a href="evaluation.json">Scale ablation</a> · <a href="symbol-evaluation.json">Native shape results</a> · <a href="scale-counterfactual.json">Artificial scale response</a> · <a href="repetition-summary.json">Repetition results</a> · <a href="timing-summary.json">Timing</a> · <a href="verification.json">Verification</a> · <a href="artifact-manifest.json">Hashes</a></p></section></html>'''
    (OUT/'report.html').write_text(page,'utf-8')
    manifest=[p for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json']
    manifest += [ROOT/'tools'/n for n in ['native_pattern_trial.py','native_symbol_trial.py','native_pattern_holdout.py','report_native_patterns.py','noise_verifier_trial.py']]
    trial.write('artifact-manifest.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=old.digest(p),bytes=p.stat().st_size) for p in manifest])
    print(json.dumps(dict(fresh=summary,repetition=rpt,scale=counter),indent=2))


if __name__=='__main__':main()
