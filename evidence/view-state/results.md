> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Viewer state verification — 2026-09-30

Implemented versioned local storage for area/zoom, both layers, opacity, OSM
context, tile progress, display tier, search, filters, sorting, page size/page,
and open panels. Storage is per browser and origin, not synchronized by account.
Explicit shared views take precedence; omitted shared-link filters use defaults.
Reloading the same saved view retains panel choices. Invalid or unavailable
storage falls back safely. Background polling does not persist stale tab views.

Private HTTPS browser check at 390 × 844:

- Selected 1916 historical map, Reduced display, OSM overlay at 1%, tile progress
  and OSM context enabled, layer panel open. Left for an evidence page and opened
  the bare app URL. Before/after URL snapshots matched exactly, including center
  24.859007,121.559000 at zoom 15. See before-reopen.png / after-reopen.png.
- Opened POI list and filters, chose Text / Newest findings / 25 per page, then
  page 2. Left the app and reopened its bare URL. Both panels and all selections
  returned; page 2 showed rows 26–50. See list-before.png / list-after.png.
- Opened a separate explicit 1924 shared view at 24.77,121.565, zoom 15. It used
  that area and layer, Top quality and default filters, with overlays off; no
  old text filter or second page leaked into the shared view.

Node behavior checks passed: round trip, reload panel state, shared-link
precedence, invalid values, unknown storage version, legacy display migration,
blocked/corrupt storage and zero-valued settings. Existing view-policy tests and
JavaScript syntax checks passed. git diff --check passed.

Static assets are live on the existing private server; reload once to load the
new viewer. No worker restart or reprocessing was necessary. These are PC browser
captures at phone dimensions, not a physical-phone test. Clearing site storage
or using another browser/device will not retain this browser's snapshot.
