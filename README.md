# Mapwalker

A local Taiwan historical-map discovery workbench. It downloads the two requested
historical layers and a modern NLSC overlay, discovers text and artificial-looking
marks, records every tile/algorithm run, and exposes source evidence for review.

**Current status:** working experimental prototype, with real Wulai inputs and
reproducible processing evidence. Not a validated landmark classifier. The first
baseline has many contour-fragment false positives and does not demonstrate useful
vegetation suppression. The evidence notebook makes these limitations explicit.

## Run

Python 3.12 is the tested runtime. Inference runs locally; no API key. The five
baseline detectors run on CPU. This PC also has an optional GTX 1650 text-region
detector, configured to use its existing isolated model environment on E:.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\start.ps1
```

Open http://127.0.0.1:8765. The web server starts a detector worker and a separate
OSM context worker. Closing the
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
- Pan and zoom across Taiwan and the offshore islands. **Taiwan**, **Wulai**, and
  the region shortcuts move the camera; **Copy view link** preserves view and filters.
- **Display** offers Top quality only (first-visit default), Reduced, All candidates,
  and Adaptive density. The choice is remembered and included in shared links.
  Ranking is automatic and unvalidated; it never needs manual labels. Zoom in for
  more candidates or choose All candidates to remove display thinning. Historical
  trail proposals are set aside in the viewer and exports; OSM trails remain context.
- Numbered groups represent every selected finding, regardless of the list page.
  Click to zoom; coincident individual findings can fan out at maximum zoom.
- Plain map dots have no saved annotation; a **pencil mark (✎)** means an annotation
  has been saved, including notes or an OSM association. Marker colors still show
  text, symbol or excluded status. A pencil count below a numbered group reports
  how many members are annotated. Saving updates the map; drafts and hiding alone
  do not count as annotations. The marker key is also visible on phones.
- Search uncertain names with `?`, filter by feature/review/reading, sort, choose
  25/50/100 per page, and enter a page number. On phones, switch between map and list.
- Choose **Modern NLSC map**, **OpenStreetMap** or **Rudy**, then use the button below
  zoom for a quick on/off comparison. On displays the selected map fully opaque;
  Off reveals the historical map. The choice survives reload and shared links.
  Older links with partial opacity now open the comparison fully on.
- Enable **OSM mountain context · 1 km** at close zoom to see nearby structured
  trails, waterways, peaks, passes and landmarks in blue. Each historical finding
  also has an OSM evidence panel with names, tags, distances, links and snapshot hashes.
- **Find in this area** queues the selected historical layer at its native maximum,
  zoom 16, regardless of the display zoom. Both layers can be queued with the CLI.
- **Tile progress** shows complete/incomplete coverage. An unmarked area is not a
  negative finding. The Background work tab lists recent jobs and failures.
- Click a finding for historical/NLSC/mask crops, approximate coordinates, detector
  fingerprint, exact source URLs, SHA-256 input hashes and timing breakdowns.
- Selecting a finding fits its complete bounds with context and opens a map-visible
  annotation panel. Desktop list and editor panels expand with window width;
  **Filter & sort** opens list filters on demand. The compact editor keeps common
  fields together; OSM suggestions open on demand while the saved link stays visible.
  Enter the **Full label on the map**, including characters the
  detector missed; use `?` for unreadable characters and do not fill gaps from an OSM guess.
  Choose POI, Not sure, or Noise, then **Save annotation**. This also updates the
  searchable reading and review status (confirmed, uncertain, or rejected).
  **Select on map** exposes nearby detection pieces regardless of display filters.
  Tap to group them, or remove a selected piece with ×. Saving applies the text,
  classification, direction, notes and OSM association to every selected piece.
  Removing a piece detaches it from the group while preserving its saved annotation.
  **OpenStreetMap link** ranks up to 12 candidates from nearby mountain
  context within 1 km (at most 200 nearby features). Names and historical aliases
  are compared when at least two characters are known; distance is measured to
  object geometry. Preview and select a candidate, or paste an OSM URL, then click
  **Save annotation** to store the association. The inspector always shows the saved
  object name, type and ID with a link; pending selections and removals are explicitly
  marked **not saved**. **Undo link change** restores the saved choice. Associations
  are stored in Mapwalker's annotation database; they do not edit OpenStreetMap.
  Suggestions are unverified and never replace the entered text automatically.
  Enter names in normal reading order, including historical right-to-left Chinese
  or Japanese. Direction defaults to automatic: compare at least two distinct,
  unambiguous OCR glyph matches with the entered reading and their map positions,
  including selected fragments. The result appears below the label and is recomputed
  on Save. Missing, repeated, conflicting or diagonal evidence stays unknown. Override
  automatic direction under **Direction, notes & history** when needed. Direction
  provenance and matched glyphs are saved with the annotation. This uses existing OCR;
  it does not recognize unread glyph images. Arabic/Hebrew input uses automatic
  display direction. Annotations are append-only, survive restart, and are included
  in GeoJSON exports. Noise uses the rejected review filter; raw detector results remain intact.
- **Hide for now** removes only the selected POI/pieces from the normal map and list.
  It saves a separate, reversible visibility history without changing text, annotations,
  review status, grouping or OSM links. Unsaved annotation edits stay in the editor.
  Under **Show**, choose **Hidden for now** to revisit these POIs, then **Restore POI**.
  Hidden/all views select All candidates and Include excluded so display ranking and
  detector exclusion do not conceal saved hidden POIs; other filters and the current
  map extent still apply. List, map counts, search and export use the same visibility
  filter. Hiding does not identify or hide other occurrences of a similar symbol.
- **Include excluded findings** exposes suppression decisions for review. Independent
  Confirm / Reject / Uncertain assessments are append-only and never fed to inference.
- **Export** downloads GeoJSON using the same search and filters as the list. Up to
  10,000 findings per export; zoom in for larger sets. Review verdicts are included.

The project prioritizes mountains; developed-area findings remain excluded by
default. OSM context never automatically renames, confirms, scores or moves a
historical candidate. Historical displacement and incomplete modern mapping
prevent treating proximity or absence as proof.

The viewer uses bundled Leaflet 1.9.4 and Leaflet.markercluster 1.5.3. For dense
views the server returns counted spatial groups, retaining every finding while
bounding the map payload. Search, map, list and export share one selection layer.
Visual evidence and the measured query experiment are in
[`evidence/viewer/report.html`](evidence/viewer/report.html).

OSM raster tiles are requested directly for interactive viewing, with browser
caching and visible attribution; there is no bulk OSM tile downloader. Structured
Overpass context is queued separately, one request at a time, with a 30-day cache
and five-minute failure backoff. Raw snapshots and the versioned queue are under
`data/osm` on the configured data drive. `--no-worker` disables both background
workers; already cached OSM context remains readable. OSM geometry is approximate
modern support, licensed ODbL, and stays separate from historical detection records.
The web viewer/queue extent includes Matsu up to 26.5° N; the existing CLI batch
validator retains its original 26° N study limit.

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
   Version 0.2 splits projected chains at links that the dash graph did not accept,
   so projection ordering cannot draw shortcuts between branches.
5. `angled-text`: ±45-degree text passes, with polygon coordinates transformed back
   to the original tile. The 溪 development probe improves from upright OCR's K to 溪.
   This does not establish overall accuracy. Overlapping readings from the two angled
   passes retain alternatives; upright and angled algorithms retain separate provenance.

An optional sixth algorithm, `text-regions`, uses pretrained CRAFT character
regions at two image scales and six rotations, without attempting transcription.
The original-scale proposals remain intact; compact higher-scale additions recover
some isolated glyphs. Empty readings display as **Unread text**; no character count
or known name is inserted. Read a crop manually, using `?` for any unreadable
characters. A text-like symbol can also be proposed by this detector.

Enable this only with a tested local CUDA runtime and checkpoint. The local
`.mapwalker-local.json` has a `text_regions` object with `enabled`, absolute `python`
and `weights` paths, and exact `packages` versions for torch, easyocr, numpy,
opencv-python and Pillow. This PC is configured to reuse `data/model-trials`.
Startup requires the configured files; each job verifies package and weight
identity, and fails visibly if the GPU/runtime is unavailable. No automatic model
downloads or silent CPU fallback occur. Set `enabled` to false and restart to
disable it; the version ledger preserves old runs. Other installations remain
CPU-only by default.

GPU inference is sequential and isolated per tile, releasing GPU memory on exit.
The model takes roughly five seconds per padded tile plus model/process startup;
the worker records both. All 116 existing sample tiles are eligible for the new
algorithm; normal algorithm fingerprint changes queue fresh work automatically.

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


## Uncertain names and search

Use **?** for each unreadable character (for example `?ライ社`). Katakana `ロ`
and Kanji `口` remain literal characters. Entirely unread regions need not invent
a name or character count.

The sidebar searches the current map view and selected historical series. A query
for `ウライ社` finds `?ライ社` and offers `ウライ社` as an unverified suggestion from
your search. Matching also normalizes width and Hiragana/Katakana and tolerates
limited spelling errors. Exact matches rank first; search pagination and export
use the same filter. A query with only unknown characters requests more detail.

Open a finding to save a tentative or verified reading. Suggestions only fill a
draft until explicitly saved. Reading revisions are separate from raw OCR and
finding reviews; unknown characters prevent marking the complete reading verified.
Local suggestions use the query and nearby complete saved/OCR readings, with
provenance. They are not an external gazetteer or historical identification.

Review the implementation evidence at `/evidence/uncertain-search/report.html` and
the detection-first experiments at `/evidence/symbol-first/report.html`.

The next comparison is `/evidence/detection-round2/report.html`: 23 frozen scenes,
text-region coverage 7/10 to 8/10 on the known development marks, and a trail
geometry correction with unchanged 23% coverage of one manually traced chain.
Symbol alternatives and their regressions are preserved. Partial references and
overlapping tile halos do not establish general precision/recall. Contour false
positives and the hot-spring detection gap remain unresolved.

## Phone and private internet access

The phone layout now provides collapsible layers/places and list filters, larger
touch controls, full-height findings, and full-screen source evidence. See
[private internet access setup](docs/public-access.md) for Google sign-in,
account restrictions, HTTPS tunnelling and external verification. Public access
requires a real Google web client and registered HTTPS origin; the default
local listener remains local-only. A temporary private-code deployment is also
available without Google registration; see the setup guide for expiry and
rotation. Live-access verification: `evidence/public-access/report.html`.
Earlier phone layout checks: `evidence/mobile-access/report.html`.

## Display levels and tile loading

Display selection `display-1` uses raw automatic text/shape evidence, then budgets
per fixed 128-pixel geographic grid cell at the display zoom. Top: floor 0.74, one
per cell; Reduced: floor 0.50, five; Adaptive: floor 0.38, two. Adaptive accepts
weaker candidates in sparse areas while limiting crowded cells; it does not fill
every cell. Unread text can qualify. These are display priorities, not calibrated
probabilities or evidence of improved detection accuracy. Filters/search run before
selection; map, paging and export use identical IDs. Stored proposals are untouched.
Legacy API requests still default to all proposals; the viewer explicitly supplies
`display`, `display_zoom`, and `include_trails=false`.

Tiles are downloaded in full, verified, and saved on E: when viewed or processed.
This is not a complete Taiwan download. The Wulai review viewport (see the evidence
JSON for exact bounds) is cached at zooms 5–16 for both historical layers and NLSC:
189 tiles verified, 50 newly fetched. Historical layers overzoom native zoom 16;
NLSC zooms 17–19 and areas outside the cached viewport remain on demand. Existing
immutable cached viewer tiles now bypass a lock held by slow new downloads, while
retaining SHA-256 validation. First-time downloads remain serialized and throttled.
No bulk OSM raster download is performed.

Actual phone/desktop screenshots, selection counts, tests, cache scope and limitations:
[`evidence/display-levels/report.html`](evidence/display-levels/report.html).

## Phone zoom and individual features

Pinch zoom can temporarily produce fractional levels. The viewer rounds request
zoom and waits for motion to end before refreshing; the API also accepts bounded
fractional view zoom for already-open clients and quantizes half-up. Error messages
are concise, dismissible, and cleared on map movement.

Marker grouping radius is 40px below zoom 13, 24px at zooms 13–15, and 16px at
zoom 16+. Tap a group of up to 12 actual findings to spread them apart immediately,
then tap an individual marker to open its evidence. Larger/aggregated groups zoom
in. This changes presentation only; display-level selection and list/export counts
are unchanged. Phone comparisons and the exact reported error reproduction are in
[`evidence/phone-map-fix/report.html`](evidence/phone-map-fix/report.html).

## Discovery progress and empty results

The work bar describes the current source and visible area. It shows completed
algorithm checks, waiting/failed work, fully finished tiles, and an active step with
elapsed seconds when present. The bar is visible on phones. Its percentage counts
completed checks, not elapsed time; there is no guessed ETA. Progress is polled
every five seconds. Newly completed checks trigger a findings refresh; results from
finished algorithms are published even before all checks for a tile finish.

Clicking Find again does not duplicate jobs and no longer implies completion.
Acknowledgements distinguish queued, paused, failed and completed areas. Background
work retains global queue details; the map distinguishes work happening elsewhere.

A zero-result view explains whether discovery is incomplete, candidates are hidden
by display mode, current search/filters reject matches, proposals were excluded, or
a completed search produced no candidates. Contextual actions reveal all candidates,
clear filters, show excluded proposals, or open background failures. A completed run
with no detections is not proof that the map contains no landmarks.

Review real queued, completed-hidden, revealed and completed-empty screenshots in
[`evidence/discovery-progress/report.html`](evidence/discovery-progress/report.html).

## Synthetic-only mark adaptation

The optional text-regions runtime now supports `profile: "synthetic-map-v1"`.
This uses a locally generated checkpoint from `tools/synthetic_craft_decoder.py`:
256 procedural images, random Kanji/Kana font glyphs, rotation, fading, blur,
contours and repeated loops; 1,200 fixed training steps with the CRAFT backbone
frozen. No historical-map pixels, user annotations, place names or evaluation
references enter training. The checkpoint, original weights and caches remain on
E:. The local runtime config names the checkpoint and profile; their identities
and policy code enter the text-regions fingerprint. The other five versions do
not change. Original behavior remains available with `craft-original` and the
original checkpoint.

The adapted detector retains peaks >=0.95 without OCR. Two distinct supported
rotations increase automatic display priority; repeated scales of one angle do
not count as separate support. Single-angle marks remain available in lower
display levels. Neither the score nor rotation agreement is verified POI accuracy.
The developed-area mask, ownership rule, coordinates and stored reviews remain
unchanged. Reprocessing follows the existing background version ledger.

Known localization improves from 8/10 to 10/10 development marks and 4/5 to 5/5
glyphs in the first fresh label. Across seven selected background regions,
retained false proposals fall from 25 to 17, while Top-eligible false proposals
total 8 before and after, distributed differently. Some crops regress; the
hot-spring is retained but has insufficient rotation support for Top quality.
These small, partial evaluations do not establish Taiwan-wide recall or precision.
Density selection can still hide eligible proposals at wider zooms.

The [round 3 image report](evidence/detection-round3/report.html) includes original
pixels, all 23 comparisons, failure cases, exact display-policy scoring, rejected
alternatives, checkpoint identity, 113 tests, production-output parity and normal
worker publication. Model files are not committed: reproducibility requires the
recorded original checkpoint, CUDA environment and installed font hashes. Font
coverage and historical typeface coverage were not exhaustively validated.

## Rudy enhanced hiking comparison

Choose **Rudy · enhanced hiking map** in Comparison layer and increase opacity.
The actual Rudy Taiwan Mapsforge map renders locally with a maintained
bochengsiong-style theme. Installation, attribution, theme policy and upstream
update workflow: [styles/rudy/README.md](styles/rudy/README.md).

## Automatic updates

The local and private startup scripts apply edits automatically. Interface edits refresh the viewer, Python edits drain active work before reloading, and Rudy style edits rebuild on demand. Use `-NoReload` to disable. See [live update behavior and limits](docs/live-updates.md).
