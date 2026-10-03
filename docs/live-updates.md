# Automatic updates while editing

`start.ps1` and `start-tailscale.ps1` now enable automatic updates by default.
Use `-NoReload` for a stable session, or pass `--reload` when launching
`python -m mapwalker serve` directly. Public startup remains opt-in.

The startup scripts locate Python in the project `.venv`, then
`%TEMP%\mapwalker-runtime`, then `%LOCALAPPDATA%\Temp\mapwalker-runtime`.
The final fallback retains access to an existing environment after Windows TEMP
is moved to another drive. A missing runtime stops startup with an installation
message; the scripts do not install dependencies or alter authentication.

- HTML, JavaScript and CSS edits refresh an open viewer after about two seconds.
  Map position, selected comparison layer, opacity and filters use the existing
  saved-view state. Refresh waits while a dialog is open, a form field has focus,
  or the tab is hidden. Close the dialog or finish editing to apply the update.
- Python edits automatically replace the server child. The supervisor retains
  the loopback listening socket, data folder and authentication mode. Discovery
  and OSM requests finish before shutdown, so a long job can delay a reload.
  Windows uses a shared event and selector loop; it does not rely on console
  signals, which fail for hidden processes in this environment.
- Rudy policy, upstream theme and symbol edits refresh the viewer. On the next
  tile request, Mapwalker validates and regenerates the maintained theme, then
  replaces only its renderer and selects a fresh content-keyed tile cache.
  Invalid edits leave the previous generated file intact and return an error
  until corrected. Generated theme writes are atomic and excluded from the
  watched inputs, preventing a rebuild/refresh loop.

The watcher covers Python files under `mapwalker/`, assets under `web/`, and
Rudy style inputs. Downloads, databases, caches, logs, evidence, environment
variables and access configuration are not watched. Dependency and access-policy
changes still require a deliberate restart. Map downloads remain explicit; stop
the app before replacing a map file held open by Java on Windows.

The revision endpoint follows the existing authentication boundary and responses
are not cached. Live-mode assets revalidate on refresh. No new network listener,
Funnel or public exposure is introduced. Python modules are reloaded in a clean
process rather than mutated while requests are using them.

Validation: targeted Python tests cover revision scope, asset revalidation,
draining active work and style invalidation/failure. JavaScript checks cover
refresh, open-dialog deferral, reconnect and hidden tabs. A live Windows process
test confirmed the server loaded an edited Python file without manual restart.

Change type: development workflow feature and renderer lifecycle change. The
main risks are interrupted jobs, lost edits, stale assets and restart loops;
the finish-before-exit lifecycle, edit deferral, cache policy and narrow watched
paths address these risks. There is a brief request delay during Python startup
or first render after a style change; this is automatic reload, not zero-downtime
deployment.
