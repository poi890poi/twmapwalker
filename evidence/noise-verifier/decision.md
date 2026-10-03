> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Decision: establish separate noise classes; do not deploy suppression yet

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
