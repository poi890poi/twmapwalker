> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# 八通關古道 named-route review

The user found no visible historical correspondence in the initial Wulai overlay and requested a notable historical trail, 八通關古道. This replaces the review location, not the detector. No historical-match claim is inferred from OSM membership.

Diagnosis: the old review used only a small town-area bounding box and highway categories, with no hiking-relation membership. Eight of its ways already had difficulty/visibility tags, so it is incorrect to say it excluded all hiking trails. A broader Wulai audit found 17 walking/hiking relations, but this work was superseded by the explicit request for 八通關. The incomplete Wulai follow-up is not delivered as a fix.

Fetch: exact OSM hiking relation 13678191 (八通關古道), then all 57 member ways using `way(r)`, regardless of names or highway categories. Preserve relation order, membership IDs, member roles and way tags. Do not include the similarly named protected-area boundaries, grassland, helipad or separate summit route. Every required member must be returned or the builder fails. Geometric gaps remain separate; no connections between different ways are fabricated.

Output: 267 immutable review pieces B001–B267, at most 180 native z16 pixels each (approximately 394–395 metres). The page opens around B008 in the western section. It loads historical tiles as the user pans along the full route; it does not download all Taiwan or launch detection jobs. It can isolate a piece, hide the ink-obscuring overlay, show full OSM way IDs and switch map series. Old S IDs remain unchanged.

Historical interpretation: the park distinguishes Qing-era 八通關古道 from the Japanese-era 八通關越道路. The modern OSM relation name alone does not identify a piece as Qing or Japanese. Primary reference: https://www.ysnp.gov.tw/StaticPage/AncientRoad . The 1916 sample contains cartographic imagery. The downloaded 1924 western sample is blank paper, so 1916 is the default; this does not prove that the entire 1924 route extent lacks imagery. No historic alignment correction was applied.

Evidence: Overpass response hashes and query details are preserved, along with the full member-way snapshot, segment mapping, 32 cached historical tile records, original image hashes and numbered images for both layers. OSM attribution: © OpenStreetMap contributors, ODbL. Historical imagery: 中央研究院 GIS.

Verification: regressions cover inclusion of unnamed/non-path route members, exclusion of nonmembers, fail-closed handling of absent members, and preservation of geometry gaps. Also validate all 57 source way IDs appear among the 267 pieces and all piece lengths are bounded. Browser checks cover the private HTTPS page, actual historical tile loading, selecting and isolating a B ID, hiding overlay ink, and the phone layout. Optional local note export is not part of the required review flow and remains unverified.

Results: 3 regression tests passed. Private page loaded 6 native 1916 tiles around B008; isolation left exactly B008 visible; hiding the overlay removed all SVG path geometry and ID labels. Switching to 1924 preserved B008 and displayed the western-sample blank-imagery notice. The page was restored to 1916 after the 390×844 phone check. Screenshot: `mobile-review.png`. Historical correspondence is still pending the user's review; these checks establish rendering and OSM membership only.

Scope and risk: review tooling and static artifacts only; production detector, queue priorities, stored POIs and previous user reviews are unchanged. User feedback is review evidence only, not a new training-label requirement. The unnamed modern trail segments may be reroutes; the user will assess historical correspondence independently.
