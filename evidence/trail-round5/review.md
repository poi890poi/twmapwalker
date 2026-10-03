> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Dense trail evidence: experiment 5

Type: experimental tooling and evidence. No production detector or stored POI changed.

## Decision

Retain the first learned likelihood for further research, but reject both complete pipelines for production. It recovers recognizable portions of the 1924 Jinshuiying historical trail where the prior graph often followed nearby contours. That limited visual improvement also appears in the new eastern window. It does not generalize cleanly to Hapen, Nenggao or the 1916 drawings: many contour fragments remain and true trail sections are missing.

The second training variant adds printing degradation and cliff-comb negatives to the generated drawings, while retaining the architecture, seed, optimizer, training duration and inference/tracing thresholds. It loses useful Jinshuiying segments and does not resolve the other development failures. Reject it at development; do not consume the displacement challenge or fresh holdout with that variant.

## Evidence boundaries

Historical pixels alone feed the learned model. There are no manual training labels, pretrained weights or OSM-derived training masks. A fixed 160-pixel-radius OSM area is applied after likelihood inference, as a separate experiment. A shifted control moves that area 320 pixels north. These areas restrict where proposals survive; they are not historical ground truth, do not move predicted pixels and cannot generate evidence from zero likelihood. Their candidate counts do not measure accuracy.

The user's Hapen displacement and Nenggao/Jinshuiying acceptance are area-level review statements with no specified layer or pixel trace. They inform case selection, not optimization targets or pixel-level evaluation. The three earlier areas are development/review cases, not fresh validation. The new window starts exactly four native tiles east of the Jinshuiying window, with the same y coordinate and no shared tiles. Its location was recorded before imagery was downloaded; the model was not tuned on it.

The base model's generated validation precision/recall are about 84.5% / 86.5%. The worn variant's own generated validation scores are about 53.2% / 72.0%. Those validation images and targets differ between generators, so this is not a same-input comparison of the models and says nothing quantitative about real-map accuracy. The actual candidate comparison uses the same frozen historical images. No real-map precision/recall is claimed.

## Cost and provenance

Architecture: 66,937 parameters, roughly 0.3 MB saved weights. Both training runs used the GTX 1650, 1,024 generated 192-pixel training patches, 128 generated validation patches, 1,000 updates, batch eight and seed 5101. Base generation took 21.7 s and training 61.9 s; worn generation 24.1 s and training 61.0 s. Peak PyTorch allocation was about 440 MB, not total device usage. Background discovery was restored after each run.

Likelihood inference alone takes roughly 0.13–0.33 s per 1024-square image. Startup, decoding, tracing and rendering are separate. Raw records include baseline and connection times; tracing is substantially slower than the neural pass. No end-to-end speedup is claimed. PNGs re-encoded by the experiment's Pillow build can have different file hashes; displayed originals were checked for exact decoded RGB equality with the hashed source images.

All originals, raw likelihood arrays, predicted ink, connected candidates, OSM restrictions, displaced-prior controls and rejected-model outputs remain available. Red is predicted ink retained by the chosen mode. Blue links join component centers across gaps of at most 32 pixels; these are hypotheses, not observed ink or confirmed route continuity. Entire rows of contour strokes can still satisfy this connectivity test.

## Reproduction and next experiment

Use `data/model-trials/runtime/Scripts/python.exe` with the existing PyTorch 2.10.0+cu128 environment. `tools/train_synthetic_dash.py` and `--worn` reproduce training; outputs refuse checkpoint overwrite. `tools/run_trail_round5.py` runs the base development cases; `--areas H` and `--holdout` select the challenge and new window. `--worn` uses the second checkpoint. `tools/report_trail_round5.py` regenerates the review from saved outputs and preserves source pixel identity. Checkpoint/source hashes and raw timings are in the JSON records. Both tiny checkpoints and source snapshots are included with the evidence.

Next causal hypothesis: a local dash likelihood is insufficient to distinguish a broken contour from a trail. Test longer-range periodicity and neighboring parallel-line context while holding the current likelihood and evaluated images fixed. Recovering more connected length must not be scored solely by OSM proximity or by the number/length of output paths. Keep a new independent map window for any surviving method.

Scope: no production detector fingerprint, queue policy, historical registration, authentication or live POI mutation. No trail candidates from this experiment have been added to the normal viewer.

Verification: all eight scene image sets exist; all eight base likelihood arrays have the expected native size; both published checkpoints match their recorded SHA256. Exact input hashes and displayed decoded RGB pixels were verified during report generation. Empty likelihood and a continuous solid line produce no dash chains; synthetic separated chains remain separate with links bounded to 32 pixels; a zero search area cannot create a path. The real paper control has 13 above-threshold pixels but zero connected trails. JavaScript syntax passed. Private HTTPS review checked scene/method switching, the unrun-variant state, both loaded 1024-pixel images, and phone layout at 390 x 844 with no horizontal overflow. Background discovery is unpaused. No production tests were rerun because this commit changes only experimental tooling and evidence.
