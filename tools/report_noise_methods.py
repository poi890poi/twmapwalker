"""Publish the bounded method survey and preserve positive and negative evidence."""
import html
import time
import numpy as np
import cv2
from PIL import Image,ImageDraw,ImageOps,ImageFont
from .contour_learner_data import ROOT,read,write,sha
from .contour_learner_trial import predict
from .noise_methods_features import OUT,BASE


def failures():
    rows={r['index']:r for r in read(BASE/'holdout-inputs.json')}
    failures=[r for r in read(OUT/'holdout-evaluation.json')['rows'] if r['reject'] and not r['negative']]
    labels={16:'Vegetation overlapping contours',33:'Small ring at bottom of large target',45:'Unresolved loop: must remain visible'}
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
    for f in failures:
        r=rows[f['index']]
        with Image.open(ROOT/r['context']) as im:im=im.convert('RGB')
        a,b,c,d=r['context_box'];target=im.crop((int(a)-4,int(b)-4,int(c)+5,int(d)+5))
        ImageDraw.Draw(im).rectangle(r['context_box'],outline='#d13333',width=1)
        board=Image.new('RGB',(620,378),'#fafaf5');draw=ImageDraw.Draw(board)
        draw.text((10,7),f"POI {r['id']} | {labels[r['index']]}",font=font,fill='#203b32')
        board.paste(ImageOps.contain(im,(296,296),Image.Resampling.NEAREST),(8,40))
        target=ImageOps.contain(target,(296,296),Image.Resampling.NEAREST)
        board.paste(target,(314+(296-target.width)//2,40+(296-target.height)//2))
        draw.text((10,347),'Context + target box',font=font,fill='#203b32')
        draw.text((320,347),'Target enlarged',font=font,fill='#203b32')
        board.save(OUT/f"failure-{r['id']}.png")


def main():
    failures();results=read(OUT/'development-summary.json');held=read(OUT/'holdout-evaluation.json')['summary']
    telemetry=read(OUT/'feature-telemetry.json');ft=np.array([r['feature_ms'] for r in telemetry['rows']])
    model=cv2.ml.RTrees_load(str(OUT/'dino-structure-rf.xml'))
    arr=np.load(OUT/'dino-features.npz')['vectors'][218:];gs=np.load(BASE/'guard-features.npz')['appearance-structure'][:,-18:]
    features=np.column_stack([arr,gs]).astype(np.float32);cv2.setNumThreads(1);predict(model,features)
    scoring=[]
    for _ in range(20):
        start=time.perf_counter();predict(model,features);scoring.append((time.perf_counter()-start)*1000)
    perf=dict(feature_median_ms=float(np.median(ft)),feature_p95_ms=float(np.quantile(ft,.95)),feature_max_ms=float(ft.max()),
        batch58_rf_prediction_median_ms=float(np.median(scoring)),scope='Frozen DINO GPU features exclude PNG decode; separate warmed CPU forest scoring of58 rows excludes fit/feature extraction',
        peak_allocated_gpu_mb=telemetry['peak_allocated_mb'],gpu=telemetry['device'])
    write(OUT/'performance.json',perf)
    names={'dino-structure-rf':'Native ROI DINO + unchanged forest','example-margin':'Nearest labeled examples','contour-patch-memory':'Contour patch memory (one-class)',
        'contour-subspace':'Contour affine subspace (one-class)','local-recurrence':'Native patch repetition'}
    table='<tr><td>Previous HOG + structure forest</td><td>16 / 96</td><td>2 / 33</td><td>0 / 58</td><td>Previous baseline</td></tr>'
    for m,s in results.items():
        decision='Winner; failed untouched safety test' if m=='dino-structure-rf' else 'Development qualifier; not advanced' if s['eligible'] else 'Rejected at development gate'
        table+=f"<tr><td>{names[m]}</td><td>{s['contour_hits']} / 96</td><td>{s['by_edition']['JM50K_1924_new']['hits']} / 33</td><td>{s['guard_hits']} / 58</td><td>{decision}</td></tr>"
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Map noise: mechanism survey and five pilots</title>
<style>body{{max-width:1100px;margin:24px auto;padding:0 18px;font:17px/1.6 system-ui;background:#fafaf5;color:#203b32}}a{{color:#24684d}}h1{{line-height:1.2}}h2{{margin-top:2em}}h3{{margin-top:1.4em}}table{{border-collapse:collapse;width:100%;min-width:740px}}td,th{{padding:12px;border-bottom:1px solid #ccd4c8;text-align:left;vertical-align:top}}.scroll{{overflow:auto}}.notice{{padding:18px;border-left:5px solid #a35330;background:#f5e9dc}}.card{{padding:16px;background:#edf0df;margin:18px 0}}img{{max-width:100%;height:auto}}small{{font-size:.9em}}summary{{cursor:pointer;font-weight:650;padding:12px 0}}code{{overflow-wrap:anywhere}}.pill{{font-weight:700}}</style>
<a href="/">Back to map</a> · <a href="../contour-curves-v2/report.html">Previous curve experiment</a>
<h1>Better visual features help. Safe noise removal still needs training that protects small marks.</h1>
<p>3 October 2026 · Literature survey + five fixed offline pilots + untouched validation + reproducibility checks.</p>
<div class="notice"><strong>⛔ Tested winner is not viable for automatic hiding.</strong> Development contour removal rose from <strong>16/96 to47/96</strong>. On48 previously unseen targets, it removed <strong>9/18 contours</strong> but also flagged <strong>2 vegetation targets and1 uncertain mark</strong>. All7 numeric and5 Han targets were retained. The survey and evidence are saved; the live detector and database were not changed. <strong>No user action needed.</strong></div>
<h2>Start with the actual image formation problem</h2>
<p>A map crop is a mixture of terrain curves, lettering, standardized symbols, print damage and scanning artifacts. Contours are meaningful structured ink; calling them “noise” describes their effect on the POI detector. It does not make them independent sensor noise. A real glyph may touch a contour, occupy only a few pixels, or lie at the edge of an oversized proposal. Small changes in native scale matter. Repeated symbols and contour loops can resemble one another.</p>
<p>The useful question is therefore: <strong>does any part of this proposed target contain a mark worth preserving?</strong> A decision based on the average appearance of the surrounding texture can answer the wrong question. “Other” and absent OSM matches cannot supply trustworthy negative labels. Modern terrain and names can corroborate a feature, but displacement and historical change prevent treating absence as proof of noise.</p>
<h2>What was actually tried</h2>
<div class="scroll"><table><tr><th>Mechanism</th><th>Contour hits</th><th>1924 hits</th><th>Separate reused protection flags</th><th>Decision</th></tr>{table}</table></div>
<p>Same218 labeled targets, five geographic folds and a two-tile exclusion buffer across editions. The baseline was replayed exactly. The forest comparison changes only the visual representation while retaining the18 structural features and forest settings. Other rows change the decision mechanism; they are separate pilots, not incremental feature ablations.</p>
<p>Each cutoff is the largest protected out-of-fold score plus0.025. Thus zero flags on the122 calibration examples is guaranteed by the rule, not independent safety evidence. That margin has different meanings for different score scales; this is a comparison of the fixed recipes, not a universal ranking of model families. Scores are not probabilities. The58 reused probes are outside fitting and cutoff selection, but prior research has repeatedly inspected them.</p>
<p>Two methods met the predeclared development gate: at least24/96 hits, more than2/33 on1924, and no reused protection flags. The forest won by1924 hits, then total hits. Only that winner consumed the48-target holdout. Predictions were locked before assistant visual labeling; the second-place method was not tested after the winner failed. No threshold was relaxed or retuned.</p>
<h3>Representation: native-scale target features</h3>
<p>The local <a href="https://arxiv.org/abs/2304.07193">DINOv2-small</a> encoder was already cached. The change is how it is used: a196-native-pixel context at1× and2× magnification, with only tokens overlapping the target pooled for the classifier. We retain size instead of squeezing every target into the same shape. This still permits context influence through transformer attention and includes background ink inside the target box. The2× input gives seven-native-pixel patch spacing; it does not recover missing scan detail. The weights were frozen, not fine-tuned.</p>
<h3>Less obvious framing: industrial defect inspection</h3>
<p><a href="https://arxiv.org/abs/2106.08265">PatchCore</a> stores normal patch features and detects departures. Here the inversion is useful: “normal” means contour texture, and an unusual mark should be preserved. <a href="https://arxiv.org/html/2405.14529v2">AnomalyDINO</a> motivates frozen visual patch matching without text prompts. Our small pilot uses nearest cosine distances to contour-only target tokens and the90th percentile, not those papers' complete systems. It caught only4/96 contours at the protection cutoff. Novelty is not semantic identity: some glyph strokes are familiar contour-like fragments, while broken contours can be unusual.</p>
<p>The <a href="https://arxiv.org/html/2602.23013v1">SubspaceAD preprint</a> models normal features by their dominant linear subspace. Our rank16 target-descriptor residual pilot caught12/96. It is deliberately smaller than the paper's giant encoder, intermediate-layer fusion, augmented patch features and adaptive rank. This rejects the tested recipe, not the paper. Nearest <em>labeled</em> examples caught25/96, suggesting that explicit protected examples are more useful here than a contour-only normality model. That interpretation is limited to these implementations.</p>
<h3>Less obvious framing: texture recurrence within a single image</h3>
<p>We matched8px and16px ink templates elsewhere in the same native-scale context, excluding every location overlapping the target and a2px margin. This directly tests repetitive texture without learning semantic categories. It caught10/96. A <a href="https://csyhquan.github.io/manuscript/21-tip-Structure-Texture%20Image%20Decomposition%20Using%20Discriminative%20Patch%20Recurrence.pdf">structure–texture decomposition study</a> explains why recurrence alone is ambiguous: both structure and texture can repeat. Our elementary matcher is not that paper's full decomposition algorithm. Fixed-size vegetation, ring symbols and repeated digits are exactly the counterexamples that require protection.</p>
<h2>The three held-out failures</h2>
<p>All30 non-contour or unresolved targets were protected by the labeling policy. The three flags below violate that policy, even though two depict vegetation rather than named POIs. Contour-only evidence does not authorize reclassifying vegetation or ambiguous symbols. Labels were made before reading these scores.</p>
<img src="failure-46614.png" alt="Vegetation symbol overlapping contours was incorrectly flagged"><img src="failure-85394.png" alt="Large box of contours also includes a small ring at the bottom"><img src="failure-114154.png" alt="Unresolved loop in a coarse contour crop was incorrectly flagged">
<p>POI85394 visibly exposes the mixed-target problem: most of its box contains contours, but the ring at its bottom must survive. This is evidence for changing the training target and aggregation rule; it is not proof that mean pooling alone caused all errors. POI114154 remains uncertain rather than being relabeled to improve the score. By edition, the model caught3/6 contours on1916 and6/12 on1924, with1 and2 protected flags respectively. The holdout contains no confirmed Kana or rare POI symbols, so broader safety remains unmeasured.</p>
<h2>Training methods worth pursuing, in priority order</h2>
<p><strong>These are researched hypotheses, not gains measured in this run.</strong> The next experiment should change one component at a time and reserve new geographic holdouts; the48 targets above are now consumed.</p>
<div class="card"><h3>1. Train “any real mark inside this box” rather than average texture</h3>
<p><a href="https://arxiv.org/abs/1802.04712">Multiple-instance learning</a>, commonly used where only whole-bag labels are available, fits our mixed boxes: a protected bag needs one convincing protected instance; a safe contour bag needs all relevant instances to be contour-like. Start with a small learned patch head and explicit conservative aggregation over frozen dense features. Do not mark every patch inside a protected box as positive: many are genuine contours. Subpatch localization and rare-symbol examples are essential; attention weights alone are not proof of correct localization.</p>
<p>A small dense convolutional encoder or <a href="https://arxiv.org/abs/1908.07919">HRNet-style high-resolution branch</a> is an architectural alternative when tokenization loses tiny Kana strokes. Its appeal is spatial resolution, not its advertised benchmark task. Test the small patch head first, then the encoder as a separate change. A larger generic vision model may still make the same aggregation error.</p></div>
<div class="card"><h3>2. Paired synthetic interventions on real contour backgrounds</h3>
<p><a href="https://arxiv.org/abs/2104.04015">CutPaste</a> motivates learning from synthesized anomalies. Adapt it using matched pairs: the same contour patch with and without a realistic digit, Kana or legend symbol, at measured native scales. Include near-miss shapes such as zero versus closed contour, ring vegetation versus hot spring, and single Kana strokes versus line fragments. The desired difference is the inserted mark; paper color and terrain must be identical across the pair.</p>
<p><a href="https://arxiv.org/abs/2004.11362">Supervised contrastive learning</a> could bring the same mark on different backgrounds together while separating matched contour-only patches. Use it as a separate training comparison. Avoid random rotations or scale normalization that erase meaningful symbol differences. Split both symbol identities and terrain sources across evaluation sets. Synthetic cut edges, modern fonts and clean ink can create shortcuts; success must be measured on real untouched map crops, not synthetic accuracy.</p></div>
<div class="card"><h3>3. Multiscale scattering before another large learned model</h3>
<p><a href="https://www.di.ens.fr/~mallat/College/TPAMI-Mallat-Bruna-Scat-CNN.pdf">Wavelet scattering</a> retains higher-order local structure that a Fourier power spectrum loses and is stable to small deformations. It is a plausible low-label alternative for separating curved line texture from corners, loops and stroke combinations. Preserve orientation and absolute scale channels; full rotation/scale invariance would destroy useful distinctions. Test a fixed scattering representation with the same classifier, not a bundle of new thresholds and features. It has not been tested here.</p></div>
<details><summary>Other methods assessed, and why they are secondary</summary>
<h3>Reconstruction with a discriminative residual</h3>
<p><a href="https://arxiv.org/abs/2108.07610">DRAEM</a> jointly learns reconstruction and anomaly discrimination from simulated defects. Applied here, the residual could indicate ink that a contour-background model cannot explain. This is richer than our failed explicit curve fit. However, a model might reconstruct the symbol too, or mistake print breaks for symbols. Defer until realistic interventions and real residual checks exist; reconstruction error alone is not a noise label.</p>
<h3>Learn from reliable positives and unlabeled data</h3>
<p><a href="https://arxiv.org/abs/1703.00593">Non-negative positive–unlabeled learning</a> offers a way to use a small trusted class without turning every unreviewed target into a negative. It addresses a real label problem, but requires credible class-prior and sampling assumptions. Our annotations are selective and “Other” mixes meanings. Defer until the sampling policy and class prior can be estimated; uncertainty should remain visible.</p>
<h3>Train for the difficult groups</h3>
<p><a href="https://arxiv.org/abs/1911.08731">Group DRO with regularization</a> emphasizes worst-group loss rather than average accuracy. Edition, native mark size and faintness are sensible candidate groups because1924 and tiny marks expose different failures. Groups must have enough examples and must capture the relevant variation. First collect balanced hard groups; a group objective cannot compensate for absent Kana or rare-symbol examples.</p>
<h3>Calibrate the cost of deleting a real mark</h3>
<p><a href="https://arxiv.org/abs/2208.02814">Conformal risk control</a> is a later calibration layer, not a better image representation. It could target expected protected-mark loss under appropriate exchangeability assumptions. Adjacent tiles, selective annotations and edition shift weaken those assumptions. A geographically separate, sufficiently large calibration set is needed; zero failures on a handful of samples is not a safety guarantee.</p>
<h3>Why ordinary self-supervised denoising is a poor direct fit</h3>
<p><a href="https://arxiv.org/abs/1811.10980">Noise2Void</a> learns denoising from noisy images under assumptions about predictable signal and noise. Contours are spatially coherent printed signal and the useful glyphs may be faint. A vanilla blind-spot denoiser can retain the contours or erase the marks we want. A structured-background reconstruction objective would be a different method requiring explicit validation.</p></details>
<h2>Resources and verification</h2>
<p>DINO feature extraction: median<strong>{perf['feature_median_ms']:.1f}ms</strong>, p95<strong>{perf['feature_p95_ms']:.1f}ms</strong>, maximum{perf['feature_max_ms']:.1f}ms per target on{perf['gpu']}. This includes both scales, normalization, pooling, transfer and synchronization; it excludes PNG decoding. Initialization was{telemetry['initialization_ms']/1000:.1f}s. Peak allocated GPU memory was{perf['peak_allocated_gpu_mb']:.1f}MiB, excluding allocator reservations and other processes. Warmed forest prediction for58 already encoded targets took a median{perf['batch58_rf_prediction_median_ms']:.2f}ms. These are offline measurements, not an end-to-end live-viewer latency claim. Per-target context encoding is redundant; tile-level feature reuse is untested.</p>
<p>All218 baseline out-of-fold scores reproduced exactly. All five pilots' out-of-fold scores and saved-state protection scores reproduced. Spatial buffers and seven invariants passed, including self-match exclusion, native-size preservation and blank-patch abstention. All48 held-out saved-model scores reproduced exactly, and structural feature extraction matched between runtimes. Six GPU descriptor/token-bank replays passed a1e-6 absolute tolerance. No model weights, packages or dependencies were downloaded for these pilots.</p>
<p>The dataset is small and previously researched. Single-seed results do not establish robustness across training seeds, editions or scanners. Assistant visual labels are not an independent human reference. Keeping unknowns protected prevents optimistic relabeling but may count true noise as protected. There is no production gain yet; the concrete outcome is a stronger offline baseline, three rejected mechanism pilots, and a narrowed training direction.</p>
<details><summary>Exact artifacts and reproducibility</summary><ul>
<li><a href="contract.json">Predeclared contract</a> and <a href="score-definitions.json">score definitions</a></li>
<li><a href="development-summary.json">Development results</a> and <a href="development-predictions.json">all development/protection scores</a></li>
<li><a href="holdout-evaluation.json">Holdout results</a>, <a href="holdout-labels.json">blind labels</a>, <a href="holdout-lock.json">prediction lock</a></li>
<li><a href="verification.json">Replay/invariant checks</a>, <a href="gpu-replay.json">GPU feature replay</a> and <a href="performance.json">resource measurements</a></li>
<li><a href="feature-lock.json">Feature hashes</a>, <a href="model-lock.json">model hashes</a>, <a href="manifest.json">package/source manifest</a></li>
<li>Run <code>python -m tools.verify_noise_methods</code> in the recorded NumPy2.2.5/OpenCV4.11.0 environment to replay fixed arrays. GPU feature extraction additionally needs the locally checksummed DINOv2-small weights, Transformers4.57.6 and Torch2.10.0+cu128. The feature collection entry point refuses to overwrite this directory; use an isolated evidence path for a new experiment.</li></ul></details>
</html>'''
    # Keep the prose readable without touching linked identifiers or filenames.
    for a,b in [('to47','to 47'),('On48','On 48'),('and1 ','and 1 '),('All7','All 7'),('and5','and 5'),
                ('Same218','Same 218'),('the18','the 18'),('plus0.025','plus 0.025'),('the122','the 122'),
                ('The58','The 58'),('least24','least 24'),('than2/','than 2/'),('on1924','on 1924'),
                ('by1924','by 1924'),('the48','the 48'),('a196','a 196'),('at1×','at 1×'),('and2×','and 2×'),
                ('The2×','The 2×'),('the90th','the 90th'),('only4/','only 4/'),('rank16','rank 16'),
                ('caught12/','caught 12/'),('caught25/','caught 25/'),('matched8px','matched 8 px'),
                ('and16px','and 16 px'),('a2px','a 2 px'),('caught10/','caught 10/'),('All30','All 30'),
                ('POI85394','POI 85394'),('POI114154','POI 114154'),('caught3/','caught 3/'),('on1916','on 1916'),
                ('and6/','and 6/'),('with1 ','with 1 '),('and2 ','and 2 '),('because1924','because 1924'),
                ('for58','for 58'),('All218','All 218'),('All48','All 48'),('NumPy2.2.5','NumPy 2.2.5'),
                ('OpenCV4.11.0','OpenCV 4.11.0'),('Transformers4.57.6','Transformers 4.57.6'),('Torch2.10.0','Torch 2.10.0'),('a1e-6','a 1e-6')]:
        page=page.replace(a,b)
    (OUT/'report.html').write_text(page,encoding='utf8')
    sources=['tools/noise_methods_features.py','tools/noise_methods_trial.py','tools/noise_methods_holdout.py','tools/verify_noise_methods.py','tools/evaluate_noise_holdout.py','tools/report_noise_methods.py','tools/contour_learner_data.py','tools/contour_learner_trial.py','tools/contour_frequency_trial.py','tools/contour_topology_trial.py']
    write(OUT/'manifest.json',dict(type='Research/tooling/documentation; no production behavior or DB change',
        impact='Frozen representation, five mechanism comparisons, first use of48 held-out targets, method survey with explicit negative results',
        risk='Repeated development selection; limited protected holdout coverage; assistant labels; preserved fixed thresholds and no automatic hiding',
        sources={p:sha(ROOT/p) for p in sources},artifacts={p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.json'},
        borrowed_inputs={str(p.relative_to(ROOT)):sha(p) for p in [BASE/'training.json',BASE/'guards.json',BASE/'folds.json',BASE/'holdout-inputs.json',BASE/'features.npz',BASE/'guard-features.npz']},
        result='Representation gains do not pass automatic hiding safety gate. Retain offline; prioritize localized protection and counterfactual training.',
        production='No detector integration, reclassification, deletion or hiding performed'))
    print('Report, three failure figures, performance and source/artifact manifest saved.')


if __name__=='__main__':main()
