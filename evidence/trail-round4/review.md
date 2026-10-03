> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Round 4 decision record

Type: experimental detection tooling and evidence, not a production behavior upgrade.

Impact: repeatable native-resolution comparisons of dash connectivity, ink threshold, thickness and a published binary road model on both historical series. OSM modern trails are shown separately and subjected to displaced-route controls. Production algorithms, their fingerprints, stored POIs, masking and viewer filters are unchanged.

Decision: reject all proposed detector changes for deployment. Connected paths often follow contour ink. Thickness eliminates output and misses trails. The Swiss pretrained checkpoint does not transfer at its published threshold. Neither repetition method improves the fixed background false-positive counts. Negative results are preserved; no threshold was selected after seeing scores.

Risk: model activations, visually plausible lines and proximity to modern OSM are not historical truth. Small Wulai-only samples do not establish general recall or accuracy. No new holdout was consumed because no candidate passed the development visual gate. The existing round-3 “fresh” and “final” mark sets are explicitly reused development material here. Sparse known references are used only after inference.

Verification: both 1024-pixel mosaics have source tile manifests and SHA256 hashes. The checkpoint's SHA256 matches Hugging Face LFS metadata. Pinned GitHub model source bytes match the downloaded architecture. Strict state-dictionary loading and RGB/255 author preprocessing were used. Actual device: GTX 1650. Model inference excludes startup time. Worker was paused for GPU testing and resumed afterwards. Existing trail path tests: 2 passed. The private HTTPS report and controls were browser-verified; no Funnel was enabled.

Scope: experiment harnesses and static evidence only. No new training dependency on user annotations, no OSM-generated historical paths, no production queue reset or fingerprint change. The optional width argument is confined to the existing experimental graph harness and defaults to zero.

Reproduction:

- Ordinary experiment Python: `%TEMP%/mapwalker-runtime/Scripts/python.exe` (OpenCV, NumPy, Pillow). GPU trial Python: `data/model-trials/runtime/Scripts/python.exe` (PyTorch 2.10.0+cu128, torchvision).
- Weights: https://huggingface.co/DominikM198/ProbRoadClass-DeepLearning/resolve/main/Binary_road_segmentation/U_Net_Resnet18_Big_Attention_Siegfried_settings_Res_U_Net_ImageNet_Swissmap2.pt ; store under `data/trail-model/road-resnet18.pt`. The harness refuses a SHA256 mismatch: `759969dc4a053a8bac9214df54fab3f6f0e6731b9c438371f838e90b344e7b81`. Weights stay out of Git. Author weights: CC BY 4.0; architecture under `vendor/` preserves MIT license.
- Pinned source revision: `09e04bb87a306e46acbf37c0df74ba28628365a1`, path `01_CNN/models/models.py`. Vendor settings record channel means 0, standard deviations 255, input 512, threshold .5. We tile native images rather than the authors' Swiss georeferenced dataset.
- `tools/run_connected_trails.py`, `tools/run_trail_width_probe.py`, `tools/run_road_model_probe.py`, `tools/run_osm_trail_controls.py`. Run against a copy/output revision: existing experiment results are guarded from overwrite.
- Mark variants: `tools/run_repeat_patch_probe.py` and `tools/run_repeat_component_probe.py`; both reuse frozen round-3 candidates and apply evaluation references only after inference.
- `tools/report_detection_round4.py` regenerates the static reports from saved outputs. It never reruns inference or adjusts thresholds.

Next causal experiment: preserve dash evidence at contour/text crossings using a dense synthetic-trained likelihood map, then compare path tracing with and without that signal. Include true curved dashes, intermittent ink, parallel contours and text as generated training cases. Only after a useful image-only baseline should OSM supply bounded local corridor hypotheses. The observed graph architecture makes component rejection at crossings a plausible failure mechanism; it has not yet been attributed quantitatively to every missed trail.
