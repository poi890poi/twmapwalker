> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# GTX 1650 trials — 28 September 2026

All five candidates ran with CUDA on this PC. None demonstrated a reliable replacement for the current discovery pipeline. The main limitation in this sample is finding and interpreting sparse historical marks, not fitting a model into GPU memory.

Open [the visual comparison](report.html) for original pixels, every OCR angle, tile overlays, YOLOE boxes, and DINO heatmaps. Models, caches and the isolated trial environment are on E:. Production POIs, masking and job versions were not changed.

## Results and decisions

| Candidate | Observed evidence | Decision |
|---|---|---|
| PP-OCRv6 small, RapidOCR ONNX export | No retained OCR output regions on the vertical-label tile in any of six rotations. The later detection-only trial exposes large boxes filtered out by empty recognition. The river tile yields individual 後 and 桶 at 0°, but supplied whole-word crops do not recover either complete name. A contour-only crop is read as `S` with score 0.66. | Reject as a production replacement under this configuration. Retain the run as a baseline for future map-specific adaptation. |
| CRAFT through EasyOCR, detection only | Finds the isolated イ region at 0° on the vertical-label tile. The other angle passes do not recover the full ウライ社 label. It supplies no reading. | Retain for further proposal experiments: this is a useful extra text fragment. Broader recall and false-positive rates remain unmeasured. |
| Manga OCR base | Reads the supplied vertical-word crop as `ウライル`, with the final character wrong. Reads isolated イ correctly at 0°. Generates `そういえば、` on a completely white image at all six angles, and unrelated Japanese phrases on the river-label crop. | Reject as an automatic fallback/transcriber. At most retain as a human-reviewed candidate reader after independent text detection. |
| YOLOE-26n-seg, two visual prompts | At the default 0.25 cutoff, two boxes total across 11 tiles: the supplied school example, score 0.257; and ウ incorrectly assigned to the school class, score 0.280. No hot-spring result, even on the reference tile. | Retain for class-agnostic proposal experiments. The ウ box is a useful artificial-mark candidate despite the wrong class; it is not a false POI merely because of its class. Reject as a complete ready-made replacement. The school response is a positive control, not an independent discovery success. |
| DINOv2 small | Produces 28×28 feature maps quickly. Visual review shows similarity/novelty responses also following contours, lettering and other background structure. There is no independently calibrated threshold or reliable separation of landmarks. | Retain as an exploratory feature representation; reject direct conversion of heatmaps into POIs. |

CRAFT and YOLOE therefore provide complementary fragment proposals worth investigating. This does not establish sufficient coverage for production. The current CPU baseline also fails the full vertical name. Its angle passes find a separate 後 near the tile boundary and a false `CCCC` on contours; these must not be counted as recovering ウライ社. Neither full-word reference, ウライ社 or 桶後溪, was read exactly by any tested recognizer at any of the six supplied rotations.

## What was tested

- 11 frozen 384×384 padded map scenes from both series; four are fresh, unannotated holdouts selected before download.
- OCR discovery: the same scene pixels enlarged 2× at 0°, −45°, 45°, 90°, 180° and 270°. Coordinates are transformed back to source pixels.
- Recognition only: eight user-marked glyph/elevation crops, two complete-label crops, a contour-only negative and a white negative, each at six rotations. These supplied crops are not discovery successes.
- YOLOE and DINO: two explicit development exemplars, 文 and the hot-spring symbol. Neither is a general test of recognizing arbitrary unseen artificial symbols. Their own reference tile is not independent evidence.
- 436 recorded calls: 138 current-baseline, 138 PP-OCRv6, 66 CRAFT, 72 Manga OCR, 11 DINO and 11 YOLOE.

Rotation, vertical arrangement and historical right-to-left order are different problems. Rotating a whole image does not assemble spaced characters into a label or establish reading order. No annotation-assisted ordering or substitution of known names was applied. A broad supplied crop can also fail where a detector's tighter crop succeeds; the recognition-only results do not contradict successful individual readings in discovery.

The OCR configurations are candidate pipelines, not an isolated test of architecture: the CPU baseline retains its classifier/0.45 discovery threshold; PP-OCRv6 disables classification and exposes scores down to zero. Raw counts and confidence values are not comparable accuracy metrics. No thresholds were tuned on holdouts, and no precision/recall claim is made for unannotated scenes.

## Costs observed on this machine

| Model / task | Calls | Median | p95 |
|---|---:|---:|---:|
| Current CPU / discovery | 66 | 209 ms | 883 ms |
| Current CPU / supplied crop | 72 | 17 ms | 18 ms |
| PP-OCRv6 CUDA / discovery | 66 | 128 ms | 2,066 ms |
| PP-OCRv6 CUDA / supplied crop | 72 | 6 ms | 10 ms |
| CRAFT CUDA / detection | 66 | 211 ms | 386 ms |
| Manga CUDA / supplied crop | 72 | 88 ms | 123 ms |
| DINO CUDA / feature exploration | 11 | 46 ms | 66 ms |
| YOLOE CUDA / visual prompting | 11 | 406 ms | 1,382 ms |

These are one-run observations with first-shape overhead, not reproducible speedup estimates. Times exclude image-file loading and rotation; they include model preprocessing, inference, decoding and, for YOLOE, repeated reference embedding. Initialization is separate and may include downloads. Tasks differ, so the rows are not a model speed ranking. Full distributions, means and maxima are in [summary.json](summary.json).

The GPU is a GTX 1650 with 4,096 MiB, using PyTorch 2.10.0+cu128. PP-OCRv6 detection and recognition sessions confirmed CUDA providers. Sampled total GPU use reached 2,158 MiB across the trials without an out-of-memory failure. Samples include desktop/other contexts and can miss brief peaks. YOLO's download/init monitoring overlapped CRAFT, violating the intended fully isolated resource measurement; its identical reported peak must not be attributed to YOLO alone. Model inference itself ran sequentially. These measurements support feasibility at the tested sizes, not a production memory guarantee.

## Reproducibility and limitations

[Input identities](inputs.json), [checkpoint hashes](weights.json), [package versions](environment.txt), [download revisions](downloads.json), [RapidOCR model registry](rapidocr-model-registry.yaml), and [integrity checks](integrity.json) accompany raw JSONL outputs and per-run metadata. Each run has an immutable harness snapshot. The final reusable runner additionally fixes a console counter that omitted YOLO's `predictions` field; raw YOLO output was always intact. It also creates its E: configuration directories before library initialization.

The first PP-OCRv6 setup attempt failed on configuration enum types; its error is preserved in `ppocr6-setup-error.json`. CRAFT's official GitHub download stalled, so a mirror copy was accepted only after its checksum matched EasyOCR's published checkpoint checksum; provenance is in `craft-download.json`. YOLO weights came from the official Ultralytics v8.4.0 release asset `yoloe-26n-seg.pt`.

This small Wulai sample is deliberately difficult and is not representative Taiwan-wide validation. It does not test trail extraction, the modern developed-area mask, historical displacement correction, DINOv3, or fine-tuned models. The next supported experiment is character-level region proposals and layout grouping, preserving unreadable text candidates for review. It should be evaluated on newly annotated tiles before enabling any replacement or claiming improved recall.

Follow-up: [Detection-first experiment](../symbol-first/conclusions.md) separates raw detector output from recognition filtering and tests CRAFT character-region proposals.
