> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Detection round 2

Two changes are running in the local app: experimental unread text regions, and
trail segments split wherever projection ordering would invent an unsupported
dash-to-dash link. The current symbol generators remain; their trail-context
protection follows the corrected geometry.

| Comparison | Result | Decision |
|---|---|---|
| CRAFT scale2 → scale3 alone | 7/10 → 7/10 known marks; gains ウ, loses full 社; median 7 → 24 proposals | Reject as replacement |
| CRAFT scale2 + rotation-supported additions | Still 7/10; does not add ウ | Reject this selection rule |
| CRAFT scale2 + compact stronger scale3 additions | 8/10, preserves all baseline regions; median 13 proposals on development scenes | Add a separate experimental text-regions algorithm |
| Symbols, cutoff 135 → 110 | 5/10 → 1/10 | Reject |
| Thick-stroke symbol groups | 5/10, different misses; first fresh glyphs 3/3 → 2/3 | Retain experiment, do not replace production |
| Broad walks over dash graph | No unsupported links, but many extra segments | Reject for this release |
| Split existing trail paths at unaccepted edges | 900 → 0 unaccepted links over 23 scenes; no new connecting lines | Land narrow geometry change |

One independently drawn cross-contour dash-chain reference remains only 95/418
pixels covered (23%) within a fixed 6px corridor. Inside its review region,
predicted pixels outside that corridor fall from 1165 to 293. That is useful
reduction, but not good trail recall or a verified route. The graph invariant is
reported separately from this manual-reference comparison.

Text regions locate all four visible glyph positions of the known vertical label
without attempting to read them. The known 溪 and hot-spring mark remain misses in
the text-region evaluation. Some contour and repeated-loop proposals persist,
especially on the degraded 1916 scans. The two follow-up groups preserve baseline
box coverage (2/3, then 2/2); second-holdout halos overlap some previous context.
No global precision/recall or fully independent spatial-test claim is justified.

The first isolated GPU job peaked at 3757 MiB. Releasing unused CUDA cache between
rotations lowered the repeat to 2615 MiB, with unchanged boxes and scores. All 23
scenes were rechecked against frozen experiment outputs after this memory change.
An isolated job took about 12 seconds, including approximately 5.8 seconds startup.
The worker records that overhead; it runs one GPU job at a time and releases the
process afterward. A single memory sample is not a guarantee under other GPU loads.

33 regression tests passed, plus five focused tests after organizing their files.
The live server publishes unread regions with detector provenance, paired map
evidence, normal developed-area gating and the existing `?` reading editor. No raw
name is invented. Previous POIs, jobs, reviews and readings were compared with the
pre-deployment SQLite backup: zero previous rows missing or changed.

The normal ledger queued 696 current tile/algorithm runs over 116 sample tiles.
The background process remains active; `verification.json` records a timestamped
progress snapshot, not a claim that the whole rescan had already finished.

Open [the visual comparison](report.html), [live unread evidence](live-unread-region.png),
[verification](verification.json), [production parity](production-parity.json), and
[memory/startup check](isolated-backend.json). Rejected and earlier memory results
remain beside the report.

## Replay notes

Baseline runtime source is Git revision fb4f53c. Frozen harness copies and source
hashes identify every run; experimental scripts use the baseline modules, so use
that revision when replaying old runs in a separate checkout. Current production
replay uses `tools/verify_detection_production.py` and the recorded local checkpoint.
Run files refuse overwrite by default. The prior environment and checkpoint
manifest remain in `../model-trials/`. All source PNG hashes are verified before
inference and again by the evidence audit.

Scene IDs can repeat between development and the second holdout. The identity is
the scene group plus ID and source/z/x/y; never join solely by scene ID. The report
and evaluator use the group as part of the key. Some original holdout-run metadata
recorded the first manifest's hash in `inputs_sha256`; `manifest-audit.json` preserves
and documents this bookkeeping discrepancy, gives the actual manifest identity,
and verifies each input image. Raw inference and input files were not rewritten.

Timing tables are experimental timings. The safe-trail prototype constructs the
graph twice; production shares the existing graph and its exact geometry was
checked on every scene. No speedup is inferred from the prototype comparison.
