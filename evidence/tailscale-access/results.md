> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Private Tailscale access — verified 2026-09-30

Decision: deploy private Tailscale Serve on the dedicated loopback port 8768.
The local worker remains on 8765. Existing public code authentication on 8767 is
kept temporarily until the owner confirms access from the phone.

The official signed Tailscale Windows installer was verified and installed.
The owner connected the PC and enabled Serve/HTTPS. Serve status reports HTTPS
443 proxying to http://127.0.0.1:8768, with no public Funnel configuration.

The real browser opened the private HTTPS hostname and the Account panel showed
the allowed account and “Private access through Tailscale.” No code was entered.
The same browser successfully submitted automatic view-priority writes through
the existing CSRF boundary. `phone-private-access.png` captures the account panel
and historical map at a 390 × 844 viewport.

Tests verify rejection of missing/wrong identity, non-loopback peers, wrong host,
wrong forwarding scheme, cross-origin writes, and missing CSRF. A session cookie
alone cannot bypass the Serve identity check. Full Python suite: 124 passed.

Physical phone enrollment/access has not been observed. Connect Tailscale on the
phone with the same account before opening the private link. The PC must remain
awake with Mapwalker running. Serve persists, but Mapwalker is not yet configured
as a Windows startup service. See docs/tailscale-access.md for restart instructions.
