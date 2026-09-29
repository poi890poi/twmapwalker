# Private access with Tailscale

Install the official Tailscale app on the PC and phone and sign in with the same
account. The phone must stay connected to Tailscale. No custom Google OAuth client
or Mapwalker access code is needed. The PC must be awake and Mapwalker running.

The local worker stays on 127.0.0.1:8765. A separate private listener on
127.0.0.1:8768 accepts only Tailscale Serve requests for the configured hostname
and account. Do not point a public tunnel at this listener. Public port 8767
continues enforcing its existing independent authentication until retired.

After Tailscale status reports Running, use its Self.DNSName as the exact HTTPS
origin. Save this configuration in ignored data/tailscale-access.json:

```json
{
  "auth_mode": "tailscale",
  "public_origin": "https://YOUR-PC.YOUR-TAILNET.ts.net",
  "allowed_emails": ["YOUR-TAILSCALE-LOGIN-EMAIL"]
}
```

Start `./start-tailscale.ps1`, then run the installed Tailscale CLI:

```powershell
& 'C:/Program Files/Tailscale/tailscale.exe' serve --bg http://127.0.0.1:8768
& 'C:/Program Files/Tailscale/tailscale.exe' serve status
& 'C:/Program Files/Tailscale/tailscale.exe' funnel status
```

Follow the CLI-provided HTTPS enablement link if needed. Enable only private
Serve, not public Funnel. Check the Serve URL on the phone and confirm Account
shows the approved email before stopping the old public tunnel.

Tailscale strips supplied identity headers and adds verified ones. The private
listener additionally checks the direct loopback peer, exact hostname, forwarded
HTTPS, and account allowlist on every request. It uses Secure/HttpOnly cookies
and CSRF tokens for writes. An existing cookie cannot bypass Tailscale identity.
Local processes are trusted; remote machines cannot directly reach this listener.
Tagged devices without user identity are denied. Use the Tailscale app to
connect/disconnect; the map does not offer a misleading separate sign-out.

Validation before rollout: tests/test_tailscale_access.py plus the existing
Google/access-code boundary tests. A simulated header test is not proof of real
PC-to-phone access; record that separately after device enrollment.

References:
- https://tailscale.com/docs/install/windows
- https://tailscale.com/docs/features/tailscale-serve
