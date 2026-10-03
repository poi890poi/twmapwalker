> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Latest-view scheduling — verified 2026-09-30

Decision: land the requested scheduling change. Detection algorithms and scores
are unchanged. Earlier FIFO ordering made revisiting a tile ineffective because
its existing job ID never changed. Each claim now consults the latest saved view.

The browser waits 600 ms after movement, coalesces requests, and promotes that
source and tile range. Views up to 256 maximum-zoom tiles are automatically queued;
larger overviews only prioritize already queued work. The current check finishes
before switching. Completed checks, retry backoff, pause, and algorithm identities
remain intact. One shared latest view applies across browsers.

## Evidence

- `phone-priority.png`: actual private HTTPS app at a 390 × 844 viewport after
  keyboard panning south. Shows 155 / 168 checks, 25 / 28 tiles, and 92% progress.
- `live-after-pan.json`: read-only production database snapshot. Job 4126 was
  running inside the newly viewed range despite older pending job 2369 and 1,758
  pending checks. This independently confirms the UI's foreground-processing claim.
- `live-before.json`: earlier snapshot in a fully searched view; the worker was
  legitimately processing another source. This is context, not a timed latency
  comparison or an interrupted-job experiment.
- `tests/test_view_priority.py`: isolated behavioral checks cover promotion over
  an existing backlog, revisit, source switch, persistence, new algorithms,
  duplicate requests, pause, retry backoff, failed jobs, and overview limits.

Validation: full Python suite 124 passed; JavaScript syntax checks and
`node tests/view_policy.cjs` passed. No detector accuracy improvement is claimed.
Phone layout was emulated on the PC; physical phone access remains unverified.

Remaining limits: running work is not interrupted. Older pending work remains
stored and resumes after foreground work. Multiple active viewers share the last
submitted scope; this is not a separate queue per user.
