> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Wulai OSM segment review

Type: review tooling. Fetch walking-path OSM ways inside the existing Wulai mosaic bounds and overlay them with stable short segment IDs. This review page is separate from the detector and does not create historical findings or training labels.

45 ways were fetched from Overpass on 30 September 2026. The first PowerShell request returned HTTP 406; the retry using the app's Python request format succeeded. `provenance.json` preserves the exact query, timestamp and response hash. OSM data: © OpenStreetMap contributors, ODbL.

Sort ways by numeric OSM ID, preserve gaps, clip each line segment to the mosaic boundary, and split continuous runs into at most 160 native pixels (about 347 metres). Number the resulting review segments S001 onward. IDs are immutable for this snapshot, shared across both historical series, and map back to full OSM way IDs and part numbers in `segments.json`.

Review risks: modern paths may not have existed historically, and historical maps have local displacement. No alignment adjustment is applied. A route can be only partly visible within one numbered segment; reviewers can describe the relevant portion. Tiny ways and stairs remain included so the user can inspect them. The page can isolate a selected segment or hide the overlay to reveal underlying ink.

Verification scope: response hash, numbering/mapping, clipping and maximum segment length, native image overlays, private HTTPS rendering and mobile interaction. Main viewer state, production detector versions and background jobs are unaffected. Browser review selections are local convenience only and are not submitted until the user copies them into the conversation.

Completed checks: 61 unique IDs; all points inside the native mosaic; every piece <=160 pixels; a line leaving and re-entering the bounds stays two separate runs. JavaScript syntax check passed. Private HTTPS loaded both 1024-pixel maps. At 390×844, selecting S010 displayed OSM way 225093433 part 2, isolated exactly one ID, and zoomed to its endpoints. Hiding Paths removed every path and label; switching the historical series retained the selected ID. `mobile-review.png` records that selection. An initial map-initialization ordering issue was fixed before delivery. Optional note export was not browser-tested and is not needed to reply with IDs in chat.
