"""Compact evidence report for localized learning, adaptation and modality coverage."""
import html
import numpy as np
from .contour_learner_data import ROOT,read,write,sha
from .local_mark_data import OUT


def main():
    first=read(OUT/'stage1-summary.json');nested=read(OUT/'nested-summary.json');adapt=read(OUT/'stage2-summary.json')
    consensus=read(OUT/'consensus-summary.json');modal=read(OUT/'modal-summary.json');diag=read(OUT/'diagnostics.json')['models']
    entries=[]
    for prefix,group in [('stage1',first),('nested',nested),('stage2',adapt)]:
        for key,s in group.items():
            d=diag[f'{prefix}-{key}-scores'];entries.append(dict(name=prefix+' / '+key,summary=s,diagnostic=d))
    table=''
    for e in entries:
        s=e['summary'];d=e['diagnostic'];q=d['quarter_removal'];z=d['zero_margin']
        table+=f"<tr><td>{html.escape(e['name'])}</td><td>{s['threshold']:.5f}</td><td>{s['contour_hits']}/96</td><td>{z['contour_hits']}/96</td><td>{d['auc']:.3f}</td><td>{q['protected_flags']}/122 · {q['guard_flags']}/58 · {q['challenge_protected_flags']}/30</td></tr>"
    training=read(OUT/'stage2-training.json');cost={v:sum(r['train_seconds'] for r in training if r['variant']==v) for v in adapt}
    epoch_counts={k:sorted({r['epochs'] for r in read(OUT/'nested-training.json') if r['method']==k}) for k in nested}
    lock=read(OUT/'stage2-lock.json');features=read(OUT/'development-feature-lock.json');times=np.array(features['feature_ms'])
    lora=diag['stage2-last-block-lora-scores'];head=diag['stage2-head-continuation-scores']
    write(OUT/'comparison.json',dict(entries=entries,consensus=consensus,epoch_counts=epoch_counts,training_seconds=cost,
        conclusion='None advances under frozen rules. Preserve40 new targets. No detector or DB change.',
        limitations='Absolute-margin failure is partly score saturation. Rank diagnostics and separate consensus prevent conflating calibration with representation.'))
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Localized small-data learning: completed experiments</title>
<style>body{{max-width:1100px;margin:24px auto;padding:0 18px;font:17px/1.6 system-ui;background:#fafaf5;color:#203b32}}a{{color:#24684d}}h1{{line-height:1.2}}h2{{margin-top:2em}}table{{border-collapse:collapse;min-width:900px;width:100%}}td,th{{padding:12px;border-bottom:1px solid #ccd4c8;text-align:left;vertical-align:top}}.scroll{{overflow:auto}}.notice{{padding:18px;background:#f5e9dc;border-left:5px solid #a35330}}.card{{padding:16px;background:#edf0df;margin:20px 0}}img{{max-width:100%;height:auto}}summary{{cursor:pointer;font-weight:650;padding:12px 0}}code{{overflow-wrap:anywhere}}</style>
<a href="/">Back to map</a> · <a href="../noise-methods-survey/report.html">Previous survey and baseline</a>
<h1>Localized heads and limited fine-tuning tested; automatic suppression still does not qualify</h1>
<p>3 October 2026 · Completed controlled training, calibration diagnostics and external-evidence audit.</p>
<div class="notice"><strong>⛔ These recipes do not meet the current automatic-hiding criteria.</strong> The separate three-model agreement pilot catches <strong>{consensus['contour_hits']}/96 contours</strong>, including <strong>{consensus['hits1924']}/33 on1924</strong>. The required minimum was24/96 and more than2/33 respectively. Its zero protected calibration flags are not independent safety evidence. The <strong>40 new geographically excluded targets remain unscored and unreviewed</strong>. No live detector behavior or database records changed. No user action needed.</div>
<h2>What changed between the controlled experiments</h2>
<p>We reused218 development targets:96 contours and122 protected or unresolved marks. The58 previous guard targets and48 consumed holdout targets remain outside fitting. Their role changes only in the separately declared consensus calibration pilot, described below. All40 new crops are more than two native-z16 tiles from693 prior contour/noise examples, with one target per geographic tile. Availability yielded16 symbol,14 name and10 numeric proposals; none were identified as Kana by automatic OCR. Proposal strata are not visual ground truth.</p>
<ol><li><strong>Ordinary pooling versus localized pooling.</strong> Every target-overlapping DINO patch is retained, without the previous64-token sampling limit. All three heads have the same384→64→3 architecture. The mean control averages patch logits; the localized head takes their maximum. Both then select the largest of three channels, allowing the same capacity. One convincing small region can therefore preserve a mixed box.</li>
<li><strong>Weak semantic hierarchy.</strong> The same localized head gains partial text/symbol bag supervision, weighted0.25. Known text supervises the text channel, known symbols the symbol channel, and contour-only bags are negative for both. Unknown marks receive only the broad preserve target. A protected box does not falsely label every contour pixel inside it as a symbol. Without this auxiliary loss, the three channels are latent and carry no assigned semantic meaning.</li>
<li><strong>Training duration chosen on separate locations.</strong> Fixed200-epoch fits saturated their scores. A second experiment used a buffered inner geographic validation split to select training duration, then refit on the entire outer fitting set. Outer test labels never chose epochs. Same optimizer, learning rate, head, labels and seeds.</li>
<li><strong>Limited encoder fine-tuning.</strong> Starting from identical nested max-pooling heads, compare20 more epochs of head-only training against the same schedule with rank4 query/value updates in the final DINO block. These add only6,144 trainable encoder parameters. The encoder prefix stays frozen and is cached losslessly. All three nested architectures tied under the original gate; the tie was explicitly resolved in favor of localized pooling without extra semantic supervision.</li></ol>
<p>Each training variant uses seeds7,19,43 and five buffered outer folds, plus a full-development fit for guards/challenges. Training target probabilities are averaged across seeds for the original calibration rule. This is a small-data pilot, not full-backbone training, a dense pixel-label model or a complete character-to-place hierarchy.</p>
<h2>Why “zero removals” needs careful interpretation</h2>
<p>The inherited cutoff is the largest protected out-of-fold noise probability plus0.025. Every learned variant has a protected score above0.975, putting the cutoff above1. This forces abstention. It does <em>not</em> establish that their rankings contain no useful information. A fixed margin in tree-vote units does not transfer cleanly to saturated neural probabilities.</p>
<div class="scroll"><table><tr><th>Recipe</th><th>Original cutoff</th><th>Hits at original cutoff</th><th>OOF hits above every protected score, no margin</th><th>Development AUC</th><th>At ≥24 contour hits: protected OOF / guards / old challenge flags</th></tr>{table}</table></div>
<p><strong>The last three columns are post-run diagnostics, not deployed cutoffs or independent validation.</strong> AUC measures overall ordering and can conceal costly tail errors. The quarter-removal column selects a cutoff from development contour scores and inspects resulting losses; it is not a newly accepted operating point. Zero-margin OOF protection is true by threshold construction. Finite-precision ties are retained. No examples were relabeled to improve any metric.</p>
<div class="card"><strong>Fine-tuning added risk without a development recall gain:</strong> at the diagnostic zero-margin cutoff, head continuation catches{head['zero_margin']['contour_hits']}/96 and LoRA catches{lora['zero_margin']['contour_hits']}/96. On the30 protected targets from the consumed challenge, their flags are{head['zero_margin']['challenge_protected_flags']} and{lora['zero_margin']['challenge_protected_flags']} respectively. Their development AUC values are{head['auc']:.3f} and{lora['auc']:.3f}. The fixed safety-margin gate rejects both. This bounds the result to this last-block adaptation recipe and tiny dataset; it does not rule out other fine-tuning methods.</div>
<h2>A separate, score-order-based calibration pilot</h2>
<p>After diagnosing saturation, we froze a new rule before evaluating it: use the fixed-duration localized heads, and flag a target only when <em>all three seeded models</em> score it above every protected calibration example. Each seed's cutoff includes122 protected OOF targets,58 guards and30 protected targets from the already consumed challenge. Thus210 examples now calibrate this pilot; none should be described as an independent safety test for it. Shared training data also means model agreement is not independent expert corroboration.</p>
<p>The result is{consensus['contour_hits']}/96 development contour hits,{consensus['hits1924']}/33 on1924 and{consensus['challenge_contour_hits']}/18 on the consumed challenge contours. It fails the fixed advancement gate, so it never touches the40 fresh crops. This sequence is recorded separately from the original experiment; we did not silently replace the cutoff or weaken the fresh acceptance rule.</p>
<h2>Ambiguous marks limit the current localization model</h2>
<img src="limiting-cases.png" alt="Three previously uncertain targets that receive high noise scores from the nested localized model">
<p>These are the three highest-scored protected development targets for the nested max head. They were labeled uncertain before training and remain protected. The coarse scan and contour-like shapes are part of the problem: a symbol-presence objective still needs evidence that distinguishes a mark from its background. Their disagreement is not proof that the labels are wrong, nor proof of losing three confirmed POIs. At25% development contour removal, this nested max model flags two uncertain targets; the weak-hierarchy version flags one. Those cutoffs remain diagnostic only.</p>
<h2>What multimodal evidence can currently contribute</h2>
<p>We audited automatic OCR plus cached OSM, the installed MOI natural-name gazetteer and the installed <strong>{modal['native_terrain'].get('native_resolution_m','unknown')}m DTM</strong> for all324 existing targets. Manual annotations and saved OSM links never entered inference. There were{modal['automatic_readings']} targets with automatic readings,{modal['osm_cached']} with cached OSM context, and{modal['terrain_states'].get('available',0)} with available terrain. Ten artificial/reference controls have no geographic record.</p>
<p>Existing name matching supports only<strong>{modal['name_supported_protected']} protected targets</strong> and{modal['name_supported_contours']} contour targets, with one additional ambiguous name result. Neither name nor numeric/elevation matching supplies a rescue for any of the previous visual model's three protected mistakes. This audits existing evidence and matching logic, not the theoretical usefulness of terrain or a trained fusion model. We did not implement a new drift-aware terrain search or infer that absent names mean noise.</p>
<p><strong>Joint multimodal training is deferred under the staged contract.</strong> Visual protection has not passed, and the measured automatic evidence does not cover the errors that prompted this work. Dense terrain coverage is not equivalent to evidence about the identity of a tiny printed symbol. OCR and visual features also share pixels, while geographic datasets may share provenance; their agreement cannot simply be counted as independent votes.</p>
<h2>Verification, resources and limits</h2>
<p>The lossless prefix was replayed through the final encoder block. Zero-initialized adapters reproduce frozen-head logits before training. Six behavioral invariants check small-mark preservation, ignored padding, token-order invariance and frozen base weights. Saved-model score replays cover all three seeds and both spatial test targets and guard/challenge targets. Inner/outer exclusion buffers, model hashes and the untouched reserve hash are verified.</p>
<p>Encoding324 targets took a median{float(np.median(times)):.1f}ms per target (GPU encoding, ROI selection and CPU cache transfer; excludes image decode/normalization). Across18 fits each, head continuation took{cost['head-continuation']:.1f}s and final-block LoRA took{cost['last-block-lora']:.1f}s of measured training. Initialization, encoding and post-fit evaluation are separate. Peak GPU allocation in the adaptation process was{lock['peak_allocated_gpu_mb']:.1f}MiB on{lock['device']}. These are offline costs, not live-viewer latency. The roughly391MB lossless prefix cache stays in ignored local data; checksums are recorded.</p>
<p>Only four training targets are labeled Kana. Assistant visual references, uncertain marks and reused locations constrain conclusions. The external audit uses cached data and the installed20m terrain source, not an unverified10m dataset. The three failure modes to separate next are unresolved reference labels, subpatch spatial detail and preservation of mixed targets. None is solved merely by adding more parameters.</p>
<details><summary>Reproducible artifacts and recorded decisions</summary><ul>
<li><a href="contract.json">Original staged contract</a>; <a href="nested-contract.json">nested training-duration amendment</a>; <a href="stage2-plan.json">adaptation tie resolution</a>; <a href="consensus-contract.json">separate calibration contract</a></li>
<li><a href="comparison.json">All comparisons</a>; <a href="diagnostics.json">score sensitivity and limiting targets</a></li>
<li><a href="stage1-summary.json">Fixed-duration results</a>; <a href="nested-summary.json">nested results</a>; <a href="stage2-summary.json">adaptation results</a>; <a href="consensus-summary.json">agreement results</a></li>
<li><a href="modal-summary.json">Modality availability</a>; <a href="modal-contract.json">causal input restrictions</a></li>
<li><a href="verification.json">Replay and invariant verification</a>; <a href="manifest.json">artifact/source hashes</a></li>
<li>Replay with <code>python -m tools.verify_local_mark</code> in the existing model-trials runtime. It requires the local DINOv2-small weights and checksummed lossless prefix cache. Original training arrays, scripts and trained heads/adapters are versioned; base weights are reused locally.</li></ul></details>
</html>'''
    # Literal prose spacing; do not modify URLs, IDs or artifact names.
    for a,b in [('on1924','on 1924'),('was24','was 24'),('than2','than 2'),('reused218','reused 218'),('targets:96','targets: 96'),('and122','and 122'),
                ('The58','The 58'),('and48','and 48'),('All40','All 40'),('from693','from 693'),('yielded16','yielded 16'),(',14',', 14'),('and10','and 10'),
                ('previous64','previous 64'),('same384','same 384'),('weighted0.25','weighted 0.25'),('Fixed200','Fixed 200'),('compare20','compare 20'),
                ('rank4','rank 4'),('only6,144','only 6,144'),('seeds7,19,43','seeds 7, 19, 43'),('plus0.025','plus 0.025'),('above0.975','above 0.975'),('above1.','above 1.'),
                ('includes122','includes 122'),(',58',', 58'),('and30','and 30'),('the30','the 30'),('Thus210','Thus 210'),('the40','the 40'),('At25%','At 25%'),
                ('all324','all 324'),('Encoding324','Encoding 324'),('Across18','Across 18'),('roughly391','roughly 391'),('installed20m','installed 20 m'),('unverified10m','unverified 10 m')]:page=page.replace(a,b)
    # Dynamic values also need separators from adjacent prose.
    import re
    page=re.sub(r'(catches|are|is|were|took)(?=\d)',r'\1 ',page)
    (OUT/'report.html').write_text(page,encoding='utf8')
    scripts=[p for p in (ROOT/'tools').glob('local_mark_*.py')]+[ROOT/'tools/diagnose_local_mark.py',ROOT/'tools/verify_local_mark.py',ROOT/'tools/report_local_mark.py']
    write(OUT/'manifest.json',dict(type='Offline research/tooling; no production integration or DB writes',
        sources={p.relative_to(ROOT).as_posix():sha(p) for p in scripts},
        artifacts={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'},
        fresh_state='40 frozen input crops, never displayed or scored; no fresh validation claim',
        decision='No variant qualifies for automatic hiding; retain negative results and calibrated-comparison limitations'))
    print('Completed report and manifest saved.',flush=True)


if __name__=='__main__':main()
