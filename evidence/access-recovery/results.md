> Archived conclusion: raw research files and visual comparisons were removed on 2026-10-03. Any references to them below are historical.

# Verification and handoff

2026-09-30: access-code and Google authentication suites: 52 passed (44.71 s).
JavaScript syntax check and git diff --check passed. Static login changes are
served without a restart. Mobile visual check and actual password-manager save
are not yet verified; work shifted to the requested Google setup.

Google setup: opened https://console.cloud.google.com/auth/clients in the in-app
browser. It redirects to Google account sign-in; no authenticated Cloud Console
session is available. User sign-in is required to proceed. No OAuth client has
been created and the app has not switched authentication modes. Existing code
access stays active. The public origin and current code hash were verified;
no secrets are recorded in this evidence.

Official setup reference:
https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid

After Google sign-in: select/create project, configure Mapwalker branding and
identity-only access, register current HTTPS origin for a web OAuth client,
configure the returned public client ID and allow only the owner's requested
Google account, then verify a real login and unauthorized rejection. A test-suite
pass alone does not establish that real Google login works.
