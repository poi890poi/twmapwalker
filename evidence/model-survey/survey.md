> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Small pretrained models for Mapwalker

Survey date: 2026-09-28. This is a literature and hardware survey, not a model benchmark.

Recommendation: test PP-OCRv6 small first, then Manga OCR and CRAFT as independently measured additions. Explore visual-prompted YOLOE for unnamed symbols. Keep geometry and source provenance independent of transcription.

## Hardware and current baseline

Local `nvidia-smi` confirms NVIDIA GeForce GTX 1650, 4096 MiB VRAM, CUDA compute capability 7.5, driver 610.60. The current Mapwalker ONNX Runtime exposes CPUExecutionProvider and AzureExecutionProvider, but no CUDAExecutionProvider. Existing results therefore do not establish GPU performance.

Suitability below is an engineering estimate for inference on one bounded crop at a time. Published checkpoint sizes and parameter counts are not peak VRAM. None of these candidates was installed, downloaded or benchmarked during this survey. App behavior, cache and queue are unchanged. Future caches belong on E:.

## Candidates

| Candidate | Published size evidence | Proposed role and decision | Important limitation |
|---|---|---|---|
| PP-OCRv6 small detector + recognizer | 9.82 MB + 21.1 MB parameter files | First benchmark: general label localization and reading; very plausible 4 GB fit | Historical Japanese fonts, diagonal labels and RTL grouping remain untested |
| PP-OCRv5 mobile | Lightweight OCR family; approximately 5M-parameter system in its paper | Established fallback comparison if v6 integration is difficult | Published gains do not prove Taiwan-map recall |
| Manga OCR base | 444 MB checkpoint | Second recognizer for Japanese text crops, particularly vertical labels; plausible 4 GB fit | Recognizes a supplied crop; does not locate labels in a map. Language priors can produce unsupported readings |
| CRAFT general multilingual checkpoint | Official pretrained detector; exact checkpoint footprint not independently checked here | Independent text-region detector; plausible 4 GB fit at bounded resolution | Old implementation needs dependency verification; it produces regions, not transcriptions |
| YOLOE-26n-seg | Nano checkpoint available; published detection configuration has 3.9M text-prompt / 3.1M visual-prompt parameters, not full released segmentation-checkpoint counts | Experimental retrieval of symbols using visual examples; plausible 4 GB fit | Natural-image pretraining is not evidence of cartographic-symbol recognition |
| DINOv2 ViT-S/14; DINOv3 ViT-S/16 | 21M each | Frozen features for clustering, example similarity or a small trained classifier; plausible 4 GB fit on crops | Neither is a ready landmark detector. Background novelty also finds stains and unusual contours |
| MobileSAM | 9.66M total parameters | Review/annotation aid: produce a mask from a point or box; plausible 4 GB fit | Does not identify artificial marks or trace reliable trails automatically |
| Florence-2-base-ft | 0.23B parameters | Lower-priority compact vision-language comparison for region proposals; batch-one fit needs measurement | More runtime overhead; generated descriptions/readings are not geometric evidence or trustworthy historical transcription |
| YOLO26n | 2.4M fused detection parameters; training checkpoint may be larger | Small pretrained backbone for later map-specific fine-tuning | Its 80 COCO classes do not include our historical symbols; not a ready zero-shot solution |

## Primary source evidence

PP-OCRv6 documentation explicitly lists Japanese and Traditional Chinese for small/medium. Its introduction excludes Japanese from tiny, although its recognition table still includes a Japanese score for tiny. Treat that inconsistency as unresolved and select small. Published timings use other hardware and must not be presented as GTX 1650 timings. [Official PP-OCRv6 documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md).

The small model parameter files are listed separately: [detector files](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det/tree/main), [recognizer files](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec/tree/main). The v5 comparison is documented in the [PP-OCRv5 paper](https://arxiv.org/abs/2603.24373).

Manga OCR explicitly targets horizontal/vertical Japanese and text over images. Its map applicability is a hypothesis. [Author repository](https://github.com/kha-white/manga-ocr), [checkpoint files](https://huggingface.co/kha-white/manga-ocr-base/tree/main).

CRAFT estimates character regions and affinities; the official repository provides a general multilingual pretrained model and polygon output. Retaining text regions when transcription is empty is particularly relevant to our misses. [Official CRAFT implementation](https://github.com/clovaai/CRAFT-pytorch).

YOLOE supports reference-image visual prompts, avoiding a need to name every symbol. Visual prompting uses no text encoder. Prompt-free inference still relies on a built-in vocabulary; it is not unrestricted unknown-symbol discovery. The released segmentation models are larger than the detection configurations in its parameter table. [Official YOLOE documentation](https://docs.ultralytics.com/models/yoloe/).

DINO supplies visual features, so Mapwalker would need an additional proposal/scoring mechanism. DINOv2 offers a straightforward existing baseline; DINOv3 also offers a 21M small model, with access requirements and its own license to resolve at adoption. Neither satellite pretraining nor natural-image performance proves historical-map suitability. [DINOv2](https://github.com/facebookresearch/dinov2), [DINOv3](https://github.com/facebookresearch/dinov3).

MobileSAM is prompt-guided segmentation. It may help annotate marks, but mask boundaries can follow contours. [Official MobileSAM repository](https://github.com/ChaoningZhang/MobileSAM).

Florence-2-base-ft is a compact multitask vision-language model. Keep it exploratory until it improves independent map evidence. [Microsoft model card](https://huggingface.co/microsoft/Florence-2-base-ft).

YOLO26n provides a tiny trainable detector, but its standard pretrained categories are COCO objects. [Official YOLO26 documentation](https://docs.ultralytics.com/models/yolo26/).

## Required map-text behavior: rotated, sparse Kanji and Kana

User clarification: labels contain sparse, separated characters and mixed Kanji/Kana, with rotation. This is the central acceptance case, not an optional language edge case. Model selection must favor this over ordinary dense document OCR scores.

Separate character orientation from layout direction. A vertical column may contain upright glyphs; rotating the whole column by 90 degrees can make every character sideways. A diagonal label can have rotated glyphs, upright glyphs arranged diagonally, or both. Horizontal right-to-left order is a separate grouping decision. Preserve original coordinates and raw character/crop readings while testing these hypotheses.

For detection, compare glyph/short-fragment regions as well as complete text lines; wide inter-character gaps must not require a recognizer to find a complete word first. Retain uncertain or unreadable text regions as POIs. When grouping fragments, use multiple candidate baselines and local orientation, with contour/dash negatives; nearest-neighbor grouping alone can combine unrelated labels. Do not merge across historical layers.

For recognition, prioritize a Japanese-capable recognizer on mixed-script crops, with Manga OCR as a separate vertical-Japanese comparison. Neither published model support nor manga examples establish success on sparse map typography. Keep PP-OCRv6 small ahead of tiny given the documented Japanese-coverage caveat. Compare full-label and individual-glyph readings without letting linguistic plausibility invent missing characters.

Expand the frozen evaluation strata: upright vertical mixed Kanji/Kana, horizontal RTL labels, oblique labels, rotated individual glyphs, wide spacing, single characters, faded ink, contour crossings, and labels crossing tile boundaries. Include non-text dashes and contour fragments as negatives. Report detection recall and false proposals separately from Kanji/Kana reading error and label grouping/order. Search orientation on development data, freeze the chosen angle policy, and evaluate fresh holdouts rather than picking the correct angle using the answer. Report costs per original tile including all passes.

## Deployment approach for this PC

Start with one GPU worker, batch size one, and the current native-resolution tile-plus-halo inputs. Compare an unchanged CPU baseline with GPU execution on identical pixels. Begin with FP32 for compatibility; test FP16 separately for numerical agreement, memory and actual speed. Do not assume lower precision is faster.

Use an isolated GPU-enabled runtime with a build supporting compute capability 7.5. Confirm the chosen provider actually runs the graph on CUDA; installed NVIDIA drivers alone do not establish this. Use ordinary attention paths initially. Standard FlashAttention-2 CUDA targets newer architectures and its BF16 path requires Ampere or newer; a separate Turing implementation exists, but is unnecessary for the first experiment. [FlashAttention support documentation](https://github.com/Dao-AILab/flash-attention#nvidia-cuda-support).

Proposed resource gate: peak total GPU memory below 3.2 GiB during a repeated tile sweep, leaving room for the desktop. This is a target, not a measured capability. Record failures and CPU fallback, and measure both cold startup and warmed p50/p95 latency. Load large optional models sequentially rather than all at once.

## Evidence plan

1. Freeze the existing RapidOCR outputs, imagery hashes, preprocessing, source layer and modern exclusion mask. Measure detection before exclusion so modern suppression cannot conceal a model failure.
2. Compare PP-OCRv6 small detection against the current detector while holding the recognizer fixed. Separately compare recognition on identical crops. Only then test the combined pipeline.
3. Evaluate Manga OCR on the same Japanese crop set. Run CRAFT independently and measure whether it recovers text regions with empty or incorrect transcriptions. Preserve unreadable regions as candidates.
4. Use the user's marked Wulai examples as development cases. Select fresh, geographically separate holdout tiles from both layers, with at least a halo gap to prevent shared pixels; annotate without seeing candidate output. Do not tune on that holdout.
5. Measure label-region recall, false proposals per tile, character error rate, exact-label reading and reading-order correctness separately. Include blank/contour-only crops to measure invented text. Trail evaluation needs continuity and false joins, not just overlapping dash boxes.
6. If testing visual prompts or training, explicitly designate separate reference/training examples. Never reuse evaluation boxes as runtime prompts and then claim independent recovery on those same marks.
7. Freeze model revision/hash, character dictionary, runtime/provider, rotations and grouping rules in the per-tile algorithm identity. Retain old results and queue only missing new-version runs.

No surveyed model is established as an out-of-the-box solution for unnamed artificial marks, repeated vegetation, and trails on these two map series. The most useful immediate change is separating text-region discovery from successful reading; a label can remain a top-priority POI even when its name is unreadable. Full RTL name assembly and disconnected trail linking require separately evaluated geometry/grouping steps.

Documentation-only scope: the survey records candidates and proposed gates; it authorizes no accuracy or speed claim. Verification was primary-source inspection plus local GPU/runtime inspection, not inference testing.
