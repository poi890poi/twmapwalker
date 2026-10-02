# Nearby annotated names

Feature contract: the annotation editor offers up to five distinct saved POI
names whose historical-map boxes are within 500 m of the selected finding or
its saved group. Box overlap ranks first by distance; same-map references break
ties. Distances are approximate gaps between boxes, not distances to real places.
Different map editions are explicitly identified because names and alignment vary.

Only latest annotations classified POI with a nonempty informative label qualify.
Skip hidden findings, the current finding, and its saved annotation group. Collapse
duplicate groups and identical name/link suggestions. Use the minimum gap between actual member boxes,
not the empty space inside a group's enclosing rectangle.

This is a manual editing aid through a separate API. Saved annotations never enter
automatic evidence scoring, OCR, detector selection, or display ranking. A click
fills the draft name, saved classification and OSM link together. An unlinked POI
clears the previous draft link. The user saves to persist these changes; group
membership and notes remain unchanged. Automatic OCR readings still fill only
the name. Same-named references with different object identities remain distinct
choices. Late responses cannot change text or another editor. Local suggestions
remain available if external evidence fails. No schema or dependency changes.

Verify proximity across tile boundaries, group exclusion/deduplication, latest
annotation edits/reclassification, hidden and distant exclusions, map provenance,
read-only API behavior, and asynchronous draft safety.

2026-10-02 behavior change: selecting an OSM suggestion also fills its name,
marks the draft POI and selects its node/way/relation identity. Modern aliases
carry the same object's link; MOI-only records carry no OSM link. This affects
explicit editor selections only. Main risks are stale links, same-name object
collisions and late responses changing another draft. Verify draft selection,
replacement/removal, save payload/persistence and stale-editor guards. No schema,
detector or automatic matching-policy changes.
