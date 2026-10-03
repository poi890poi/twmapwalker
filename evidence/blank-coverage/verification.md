> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Verification — 30 September 2026

Type: execution coverage and performance. Scope: skip confidently blank historical owner tiles before the existing detector pipeline; record the exclusion and show it in discovery progress.

The frozen policy ignored 13/16 known paper tiles and 3/4 new adjacent paper tiles. All 43 real map-content controls were retained. Four paper tiles with ambiguous specks were intentionally retained. These bounded results do not establish Taiwan-wide recall or safety on every faint historical mark.

Validation: 131 Python tests passed (one existing Starlette deprecation warning); viewer policy and state checks passed; browser application syntax check passed. Tests cover sparse/faint mark preservation, completed blank-job bookkeeping, unchanged delegation for content, and reprocessing blank exclusions when the policy changes.

Deployment: restarted the existing local worker and private Tailscale service. The private service uses its existing Tailscale configuration; public Funnel remains off. The evidence page was opened successfully through private HTTPS.

Live verification: one confirmed paper tile completed all six algorithm jobs with the explicit blank exclusion, zero detector time, and no model initialization. Coverage reports one completed blank tile and six completed checks. The worker is resumed. See [live results](live-verification.json).

All six detector identities match the previous running service. Existing findings remain active; this change does not requeue completed content tiles. Coverage has its own source hash and human-readable version. The source bytes are preserved across checkouts so line-ending conversion cannot silently change that identity.

Risk: a sufficiently faint or tiny mark could resemble paper texture. The policy therefore retains suspicious spots and dark/ambiguous images. Further map sources and scan conditions need independent validation. The viewer still permits panning across blank coverage; this change skips discovery work there.
