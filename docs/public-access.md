# Private internet access

The phone viewer supports map/list switching, grouped findings, collapsible layer
controls, search, filters, sorting, pagination and full-screen evidence. Maps,
detection and databases stay on this PC and E:. The PC must remain awake and
connected. No offline map cache or service worker is installed in the phone.

## Google setup

1. Choose a public HTTPS hostname. A named Cloudflare Tunnel and your domain give
   a stable address. A free TryCloudflare tunnel gives a temporary random address
   that changes on restart; Google origins must be updated whenever it changes.
2. In Google Cloud Console, select a project and configure Google Auth Platform
   branding/audience. For a personal testing app, add your account as a test user
   if Google requests one. Request only identity/email/profile, no Drive or Gmail
   access. Create an OAuth client of type **Web application**.
3. Add the exact public HTTPS origin to **Authorized JavaScript origins**, without
   a path or trailing slash. This app uses a popup callback; it does not require a
   redirect URI or a client secret. Copy the public client ID.
4. Copy `access.example.json` to `.mapwalker-access.json` in the project root.
   Fill in the origin, client ID and explicit allowed email addresses. The real
   config is Git-ignored. Google must verify the email and be authoritative for
   it (Gmail or Google Workspace). For another email provider, pin the account's
   verified numeric Google `sub` in `allowed_google_subjects` instead.

See [Google's setup instructions](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
and [ID token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

## Run and publish

Install `requirements.lock.txt`. Keep the usual `start.ps1` process running on
127.0.0.1:8765 for local use and background processing. In a second terminal run:

```powershell
.\start-public.ps1
```

This starts **127.0.0.1:8767**, requires valid Google configuration, and starts no
second detection or OSM worker. It shares the existing E: data. Configuration
failure stops startup; it never falls back to an unauthenticated listener.

Install cloudflared from [Cloudflare's official download page](https://developers.cloudflare.com/tunnel/downloads/).
For a named tunnel, configure its public hostname service to `http://127.0.0.1:8767`.
Keep the origin Host header equal to the public hostname or localhost. Do not
point it to 8765 and do not open a router port. Cloudflare handles HTTPS and
forwards through its outbound tunnel. Keep the cloudflared process running.

For a temporary trial, `cloudflared tunnel --url http://127.0.0.1:8767` prints the
random HTTPS hostname. Start the tunnel to obtain the hostname, register it with
Google, fill the config, then start the public listener. Until that listener is
configured, the tunnel has no app to serve. Quick tunnels have no uptime SLA;
see [Cloudflare's limitations](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

After publishing, run an independent external check:

```powershell
.\check-public.ps1 -Origin https://YOUR-HOSTNAME
```

Then open that address on a phone, sign in with an allowed Google account, open a
finding, and sign out. Confirm a signed-out browser cannot fetch findings or
images. A successful automated token test is not a real Google account login.

## Access and recovery

Sessions expire after eight hours. Cookies are Secure, HttpOnly, SameSite=Lax;
the session database stores token hashes. Google ID tokens are never persisted.
Login uses a ten-minute single-use browser nonce. Writes additionally require
the configured Origin and a session CSRF token. Protected responses use no-store.

To revoke access, remove the email/subject from the configuration and restart the
public listener; existing sessions are rechecked against the allowlist on every
request. For an immediate shutdown, stop the public listener or tunnel. The
local worker can continue. Existing local routes also reject proxy headers.
Sessions/challenges live separately in `data/access.sqlite3`; historical findings
and processing versions are unchanged. Environment overrides are
`MAPWALKER_ACCESS_CONFIG`, `MAPWALKER_PUBLIC_ORIGIN`,
`MAPWALKER_GOOGLE_CLIENT_ID` and comma-separated `MAPWALKER_ALLOWED_EMAILS`.
