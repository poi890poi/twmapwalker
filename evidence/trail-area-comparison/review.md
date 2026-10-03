> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Three alternative trail areas

The user's rejection of the western Batongguan correspondence is retained. No offset or automatic registration was fitted to that rejected sample.

The alternatives were chosen from a new named OSM way snapshot before historical pixels were examined. For each exact trail name, select the longest connected hiking-way geometry and use its distance midpoint as the sample anchor. Each window is 4 × 4 native zoom-16 tiles, identical between the two map sources. All matching named hiking ways intersecting that window are clipped and assigned new H/N/J IDs. OSM positions are unmodified. This selection is reproducible, but is not a random sample of Taiwan or a complete hiking network.

| Area | IDs | Visual observation / decision |
| --- | --- | --- |
| 哈盆越嶺步道 | H001–H009 | The 1916 map has a conspicuous dashed route away from portions of the OSM trace. Differences persist in the 1924 comparison. Retain as a mismatch/uncertain case; do not label OSM pixels as historic trail. |
| 能高越嶺古道 | N001–N009 | The 1916 map shows a dashed route with some similar bends but visible offsets. The 1924 map has a prominent corridor near much of the OSM trace and 東能高警官駐在所 text. Retain for visual review; similarity does not establish exact correspondence. |
| 浸水營古道 | J001–J008 | The 1924 map provides the strongest candidate in this bounded comparison: much of the OSM trace follows the visible dashed historical route. The 1916 route is substantially displaced/different in this window. Review the 1924 sample first; no pointwise labels accepted yet. |

These are qualitative visual observations, not measured trail recall or registration accuracy. Confirm correspondence from unmarked historical pixels. Historical displacement, map generalization, scanning/georeferencing, route changes, and dates remain possible explanations; this comparison cannot isolate the cause. No global translation is justified.

Date context: the [park describes the Japanese Batongguan route as completed in 1921](https://www.ysnp.gov.tw/Trail/e0befc9d-0707-4ce0-b530-6bde521570f9), later than the nominal 1916 layer. This is a possible explanation for the earlier mismatch, not proof of the exact survey date of a particular sheet.

All six original/overlay pairs are published, including unfavorable comparisons. Source hashes and OSM fetch provenance are included. One final tile fetch disconnected; retry used the existing cache and completed the same frozen inputs. Scope is evidence tooling only: no production detector, queue or stored finding changed.

Verification: reproduced the frozen location selection; verified all six original-image hashes and 507 coordinate round trips; all 26 IDs are unique. JavaScript syntax passed. Private HTTPS browser review confirmed all three area choices, both layers, paths off/on, original images, and responsive layout at 390 x 844. Screenshots are preserved in browser-review.png and mobile-review.png. No production code changed, so the production test suite was not rerun.

## User review — 30 September 2026

> 哈盆 is off by few contour lines (diff elevation). Others are good.

This later direct review updates the provisional area-level decisions above: Hapen is a displaced correspondence case; Nenggao and Jinshuiying are accepted as good matches by the user. The feedback does not identify a particular layer or individual subsegment, so it is not expanded into per-layer or per-pixel ground truth. No offset or elevation difference was measured. Preserve Hapen as a challenge case for finding the historical trail across contours; use the other two for initial correspondence experiments. OSM may guide a search region, but historical ink must support any detected trail.

Change classification: review evidence and displayed review notes only. Original images, numbered geometry, detection and existing findings remain unchanged. Exact feedback and usage limits are in user-review.json.
