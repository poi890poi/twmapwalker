# Nearby annotated names

Feature contract: the annotation editor offers up to five distinct saved POI
names whose historical-map boxes are within 500 m of the selected finding or
its saved group. Box overlap ranks first by distance; same-map references break
ties. Distances are approximate gaps between boxes, not distances to real places.
Different map editions are explicitly identified because names and alignment vary.

Only latest annotations classified POI with a nonempty informative label qualify.
Skip hidden findings, the current finding, and its saved annotation group. Collapse
duplicate group/name suggestions. Use the minimum gap between actual member boxes,
not the empty space inside a group's enclosing rectangle.

This is a manual editing aid through a separate API. Saved annotations never enter
automatic evidence scoring, OCR, detector selection, or display ranking. A click
fills only the draft name; classification, OSM link, group, and saved data do not
change. Late responses cannot change text or another editor. Local suggestions
remain available if external evidence fails. No schema or dependency changes.

Verify proximity across tile boundaries, group exclusion/deduplication, latest
annotation edits/reclassification, hidden and distant exclusions, map provenance,
read-only API behavior, and asynchronous draft safety.
