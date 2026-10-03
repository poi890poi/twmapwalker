> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Detect marks before reading them

28 September 2026. **Detection first is a promising direction. CRAFT's character-region proposals are the strongest candidate in this trial.** No recognizer, known place name, school/hot-spring template, or evaluation box was used to generate them. A glyph remains a useful unread candidate.

[Open the interactive comparison](report.html). Select a map scene and click a blue region to inspect its original crop. Green boxes are independent review references, added after inference.

## Measured results

| Method | Located known marks | Median candidates per padded tile | Median total time per tile | Decision |
|---|---:|---:|---:|---|
| Current component + junction symbols | 5/10 | 116 | 141 ms, CPU | Retain as the existing baseline; broad coverage creates heavy review burden. |
| PP-OCRv6, recognition disabled | 1/10 | 1 | 4,669 ms, CUDA, six rotations | Reject this configuration as a mark proposal replacement. Low counts conceal very large, unhelpful boxes. |
| CRAFT character-region policy | **7/10** | **7** | 1,531 ms, CUDA, six rotations | Retain for further detection-first development. No production promotion yet. |
| Stable dark components across thresholds | 5/10 | 46 | 460 ms, CPU | Reject as a replacement; retain as an inspectable pixel baseline. It still proposes many contour fragments. |

The 10 references are a small, partial set of user-identified development marks. A location match means intersection-over-union >=0.25 against a fixed manually drawn box. These counts are **not Taiwan-wide recall, classification accuracy or measured precision**. All counts include the tile halo; production ownership/masking was not applied in this experiment.

CRAFT locates **ラ, イ, 社, 後, 桶, 651 and 文** without reading them. It misses **ウ, 溪 and the hot-spring mark**. Some proposals overlap each other or include nearby contours; the report preserves them. The baseline still supplies useful marks CRAFT misses, so this is evidence for a proposal stage rather than evidence to delete the other detectors.

## What changed and what the evidence explains

The previous default CRAFT output, evaluated on these same 10 fixed reference boxes, locates **2/10** (イ and 651). The new policy uses the same checkpoint, images, enlargement and six rotations but extracts connected character-score regions before word/affinity grouping. Core threshold is 0.20, minimum peak 0.30, minimum core area 5; boxes include six native pixels of context. Thresholds and grouping change together, so the experiment supports this postprocessing policy as a whole and does not isolate which part caused each added detection. It is not proof that all generic symbols are text-like.

The PP-OCRv6 wrapper really does discard detector boxes when their recognized text is empty. Turning recognition off exposes those boxes. On the vertical-label tile, however, the newly visible boxes cover almost the entire image and do not localize the characters. This corrects the interpretation of the prior result: **there was no retained OCR output; that did not establish that the detector itself returned no regions.** Disabling recognition alone is insufficient.

The stable-ink method finds components that persist across multiple grayscale thresholds. It helps some broken/light glyphs, but has no understanding of landmarks; many contours and isolated background strokes survive too. Repetition flags use shape similarity only and are not a validated vegetation filter.

## Transfer and remaining misses

All four methods ran on 15 frozen scenes: the 11 previous model-trial scenes and four new scenes from both historical series. On the new 陸測 north scene, CRAFT proposes the elevation label and other marks; it also proposes a repeated loop-shaped background mark. On the new 陸測 west scene it produces zero candidates. That is not proof that the scene contains no landmarks. The coarser 蕃地 imagery still produces spurious-looking CRAFT regions. No tuning followed these observations.

The fresh scenes are unannotated transfer checks, so no accuracy score is assigned to them. Repeated grass/forest marks, unknown pictorial symbols, false contour intersections and local map displacement remain unresolved. Dashed-trail extraction is a separate existing stage and was not replaced or evaluated here.

## Resource and reproducibility evidence

There are 60 completed method/scene runs, comprising **210 timed passes**. GPU inference ran sequentially. Sampled total GPU use peaked at **2,180 MiB** for CRAFT, below the 3.2 GiB experiment target; this includes desktop use and may miss short peaks. Image loading and rotation/resizing are outside the reported call times; model preprocessing, inference and proposal postprocessing are inside. Times are single-run observations, not repeatable speedup claims.

[Frozen inputs](inputs.json), [fixed references](references.json), [per-mark scores and timing distributions](summary.json), [CRAFT postprocessing comparison](craft-postprocessing-comparison.json), raw per-angle JSONL, run metadata and matching harness snapshots accompany the report. The model checkpoints and package versions are the same as the preceding GTX 1650 trials. PP-OCRv6's saved initialization configuration has `use_rec=true`; its recorded harness explicitly passes `use_rec=False` at inference. All data and new artifacts are on E:.

The next supported step is to refine **unread region detection and repetition rejection**, then group nearby glyphs by geometry while preserving rotated and historical right-to-left arrangements. Reading those candidate groups should be a later, optional stage. This trial changes no production POIs, background jobs, modern masks or algorithm fingerprints.
