# Mapwalker

A local Taiwan historical-map discovery workbench. It downloads the two requested
historical layers and a modern NLSC overlay, discovers text and artificial-looking
marks, records every tile/algorithm run, and exposes source evidence for review.

**Current status:** working experimental prototype, with real Wulai inputs and
reproducible processing evidence. Not a validated landmark classifier. The first
baseline has many contour-fragment false positives and does not demonstrate useful
vegetation suppression. The evidence notebook makes these limitations explicit.

## Run

Python 3.12 is the tested runtime. All inference runs locally on CPU; no API key.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\start.ps1
```

Open http://127.0.0.1:8765. The web server starts one background worker. Closing the
browser does not stop discovery. Stopping the server leaves work in SQLite; unfinished
runs are reclaimed after their 120-second lease expires. The process must be running
for discovery to continue; no operating-system service is installed.

On this machine, the disposable Python environment was created at
`%TEMP%\mapwalker-runtime`; `start.ps1` uses it when `.venv` is absent.
The map cache and database live on **E:** at `E:\workspace\mapwalker\data`, as requested.
The local `.mapwalker-local.json` records this path. An explicit data path also works:

```powershell
.\start.ps1 -Data 'E:\workspace\mapwalker\data'
```

This selects a separate database/cache. Stop the app and copy the entire `data`
directory there first if you want to preserve the sample and review history. Keep
the source until the copied application data has been verified. The downloader
stops new downloads below 16 MB free; this reserve is not a capacity estimate.

## Use

- Select **1916 蕃地地形圖** or **1924 陸地測量部（新版）**. Move the map: markers and
  the paginated side list use the same viewport and source filter.
- Slide **Modern NLSC overlay** to compare present-day development.
- **Find in this area** queues the selected historical layer at its native maximum,
  zoom 16, regardless of the display zoom. Both layers can be queued with the CLI.
- **Tile progress** shows complete/incomplete coverage. An unmarked area is not a
  negative finding. The Background work tab lists recent jobs and failures.
- Click a finding for historical/NLSC/mask crops, approximate coordinates, detector
  fingerprint, exact source URLs, SHA-256 input hashes and timing breakdowns.
- **Include excluded findings** exposes suppression decisions for review. Independent
  Confirm / Reject / Uncertain assessments are append-only and never fed to inference.
- **Export** downloads candidate GeoJSON for the selected layer and viewport. Up to
  10,000 findings per export; zoom in for larger sets. Review verdicts are included.

## Download and processing batches

```powershell
# Use the Python executable from your environment.
python -m mapwalker plan --bbox 121.544,24.850,121.574,24.875 --estimate-only
python -m mapwalker plan --bbox 121.544,24.850,121.574,24.875
python -m mapwalker status
python -m mapwalker pause
python -m mapwalker resume

# Separate web and worker processes, if desired:
python -m mapwalker serve --no-worker
python -m mapwalker work

# Estimate a broad Taiwan region before allocating disk/network resources:
python -m mapwalker plan --bbox 119.3,21.8,122.1,25.4 --estimate-only
```

The CLI accepts `--source JM50K_1916` or `--source JM50K_1924_new`; omit for both.
The default batch ceiling is 2,500 historical tiles; `--max-tiles N` explicitly raises
it. `--data PATH` goes before the subcommand. Processing uses a 64-pixel halo, so
neighbors are downloaded as context. NLSC tiles are shared between historical runs.
Downloads are paced at one new request per 0.4 seconds per process. Large rectangles
include ocean and unmapped regions; unavailable data is a visible failure, never a
successful zero-finding run. Start with small land regions. This iteration has
downloaded the Wulai sample, **not all of Taiwan**.

## Algorithms and displacement

Five independent experimental algorithms are registered in `mapwalker/detectors.py`:

1. `text`: bundled RapidOCR PP-OCR Chinese model, with 2× input upsampling. Scores are
   recognition scores, not POI accuracy. Old/vertical Japanese and blurred text can
   be missed or mistranscribed. 文 may be a school symbol rather than a place name.
2. `symbols`: compact dark connected components. Similar compact shapes occurring
   four times in the local context are marked as repeated patterns. Curves can
   fragment into apparent symbols; meaningful repeated marks can also be excluded.
3. `junctions`: clusters of branching strokes within long ink components. This can
   propose marks attached to contours, including part of the user-identified
   hot-spring mark. It also proposes some contour intersections.
4. `trails`: aligned chains of elongated dashes, shown as purple line segments and
   exported as GeoJSON LineStrings. Dashes near these chains are protected from
   repetition suppression. Trails remain important even though they repeat. These
   are local segment proposals; direction, connectivity and walkability are unknown.
5. `angled-text`: ±45-degree text passes, with polygon coordinates transformed back
   to the original tile. The 溪 development probe improves from upright OCR's K to 溪.
   This does not establish overall accuracy. Overlapping readings from the two angled
   passes retain alternatives; upright and angled algorithms retain separate provenance.

Text labels sort first in the POI list. Horizontal CJK strings include a possible
right-to-left reading without overwriting the raw OCR result. The user-identified
RTL 桶後溪 remains an evaluation example; its known name is not injected into output.

The user-identified vertical label ウライ社 is not reliably recognized by this
baseline OCR. Rotating the image did not recover it in the development experiment.
Its known reading is documented as evaluation context, never inserted as a detected
place name. Better historical Japanese OCR remains an open accuracy gap.

NLSC's lavender building-fill pixels and neighborhood density produce a developed
mask. Only its interior beyond a 16-pixel margin excludes findings. The margin is
about 35 metres at Wulai zoom 16, **not a measured historical-map error bound**.
Boundary overlaps stay reviewable. Bigger and local distortions remain unresolved.
Each historical layer keeps its own coordinates and findings. No snapping to modern
features, cross-layer merging, or fabricated symbol names. Different algorithms may
propose the same feature; provenance is retained instead of silently merging them.

## Algorithm versions and durable state

SQLite owns `tiles`, `algorithms`, `jobs`, `attempts`, `pois`, `reviews`, and `settings`.
An algorithm fingerprint hashes its name/version, configuration, relevant code,
dependency versions, bundled model hashes, and immutable imagery snapshot identifier.
Each `(tile, fingerprint)` has one job. A successful empty result is still complete.

On startup, the registry activates current fingerprints and automatically schedules
missing work for **every previously registered tile**. Old runs and review records
remain intact, while viewport queries show only current algorithm results. Shared
pipeline changes conservatively invalidate all affected fingerprints. Different
worker versions cannot claim one another's jobs. Stop/restart the server after edits.

To add an algorithm: add its spec to `specs()`, its implementation to the worker
dispatch, and its source file to the fingerprint inputs; add a behavioral test and
an independent comparison before considering its results reliable. Restart the app.
No manual clearing of tile flags is necessary. To refresh remote imagery, choose a
**new** `SNAPSHOT` identifier; never overwrite the old snapshot cache.

Claims are transactional. Workers renew leases; expired leases are reclaimable.
Publication and completion are one transaction, and stale claim tokens cannot publish.
Three failures mark a job failed; manual retry preserves attempt history. Pause is
persistent and lets the current job finish. Source images and metadata are written
atomically and verified by SHA-256 on cache reads. Original evidence uses the run's
snapshot and refuses mismatching input hashes.

This is a localhost single-user application. Keep it bound to 127.0.0.1. A public
deployment would require authentication, quotas and a different operational review.

## Review the evidence

- `/evidence/user-review/report.html`: before/after review of the eight circled
  targets in your screenshot. Their tiles were initially unprocessed. Both layers
  now have all five runs complete across the shown view (112 tiles, 560 runs).
  OCR returns 651, 後 and 桶, but still misses the vertical label and circled 溪.
  The supplied paths and complete RTL name are not claimed as recovered.
- Open `/evidence/report.html` in the running app, or open `evidence/report.html` directly.
- `evidence/experiment.json`: frozen configurations, inputs, raw proposals and controlled
  comparisons (baseline → repetition → developed mask → extra junction proposals).
- `evidence/run-telemetry.json`: actual production runs and separate I/O, decoding,
  model startup, detection and filtering timings.
- `evidence/junction-experiment.json`: two development reference boxes supplied by
  the user's symbol descriptions and visually located in the original image.
- `evidence/baseline-v1/`: preserved first run, including negative results.
- `evidence/CONTRACT.md`: acceptance criteria, causal-input restrictions and limitations.

No real-map precision/recall claim is made. The user-identified examples are development
probes. Synthetic tests establish mechanism behavior only. Fresh holdout images expose
generalization for review, but still need independent human annotations. Review labels
are never used as a runtime shortcut. A useful next milestone is a blinded annotation
set covering text, artificial marks, contours, vegetation and developed boundaries.

```powershell
python -m pytest -q
python tools/probe_sources.py
python tools/experiment_junctions.py
python tools/build_evidence.py
```

Evidence rebuilding fetches missing sample tiles, records runs, and overwrites the
current report. The initial baseline directory is retained. No remote map data or OCR
service is required for replay once the sample tiles and local models are cached.

## Verified sources

- Academia Sinica [WMTS documentation](https://gis.sinica.edu.tw/tileserver/):
  `JM50K_1916` (JPEG), `JM50K_1924_new` (PNG).
- The publisher's [layer settings](https://gis.sinica.edu.tw/tileserver/onlinemapsources.xml)
  specify maximum zoom 16 for both layers. Generic WMTS matrices reaching zoom 21
  do not establish native layer resolution.
- NLSC [WMTS capabilities](https://wmts.nlsc.gov.tw/wmts/1.0.0/WMTSCapabilities.xml):
  `EMAP`, GoogleMapsCompatible, row before column in the tile URL.
- The downloaded metadata snapshots are in `evidence/sources/`. Attribution remains
  visible on the map and paired evidence. Leaflet 1.9.4 is bundled with its license.
