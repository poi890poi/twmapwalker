# Rudy / bochengsiong maintained hiking layer

The browser comparison layer renders the **actual Rudy Mapsforge Taiwan map**
with a maintained hiking theme, through an app-owned loopback MapsforgeSrv.
It is separate from detection: NLSC still owns the developed-area mask and
historical evidence. The opacity control works for all three comparison layers;
100% displays the modern map alone underneath historical findings.

## Ownership and modifications

`upstream/MOI_OSM.xml`, `upstream/moiosmhs_res/` and `upstream/License.txt`
are the untouched official Rudy **2026-10-01** hillshading theme archive.
`reference/bochengsiong.xml` preserves the user-requested older style and its
attribution. Do not overwrite the current theme with that old file: it lacks
many current rules and points to a different asset directory.

`enhancements.json` is the small maintained policy. `mapwalker/rudy_style.py`
generates `upstream/bochengsiong.xml` beside the assets, with these changes:

- Carry forward bochengsiong's saturated `#1E90FF` water palette; increase water
  line widths by 1.5 and darken name text to `#146CB4` for contrast.
- Increase path/footway/steps/bridleway line widths by 1.5, retaining current Rudy
  difficulty colors, dash patterns, access rules, tunnel rules, zooms and labels.
- Increase survey, heritage and camping/hut symbols by 1.25, using integral
  dimensions required by Mapsforge. Keep current upstream icons and predicates.
- Remove repeating attraction-area patterns while retaining point labels/icons.

These are deliberate ports of the old theme's intent onto current Rudy rules,
not a claim that every old styling edit has been copied. No route data is added.
Hillshading is not enabled without DEM data; contours remain available.
The generated build report records affected counts and SHA-256 hashes. Missing
rule families or missing assets fail generation, requiring an update review.

## Install and use

Install Java 17 or later and run `./tools/setup-rudy.ps1`. Map and renderer stay
under ignored `data/rudy/` (about 400 MB for the map; installer archive also uses
space). Renderer 0.30.0.0 is pinned with its SHA-256 in the installer. The theme
and resources are part of this project. No extra Java libraries are needed.
Restart Mapwalker, choose **Rudy · enhanced hiking map**, then increase opacity.
For another data folder, pass `-Data <folder>` to the installer.

Mapwalker starts the renderer lazily, binds only `127.0.0.1` on a private dynamic
port, and stops it on app shutdown. The browser uses authenticated Mapwalker
routes, never the renderer port. Existing Tailscale Serve remains the private
entry point; no Funnel or new public listener is needed. First render includes
Java startup and map hashing, typically around 12 seconds on the development PC.
Disk tiles are keyed by map, renderer, theme and asset content; browser responses
revalidate. Missing installation or render failure returns 503, with a UI message.

## Update Rudy without losing the enhancements

1. Stop Mapwalker before replacing map data. Run
   `./tools/setup-rudy.ps1 -UpdateMap`; it records download and map hashes in
   `data/rudy/installation.json`. Map updates are explicit, never automatic.
2. Download the new official Orux/Mapsforge **hs_style.zip** from
   https://rudymap.tw/ (currently
   https://moi.kcwu.csie.org/MOI_OSM_Taiwan_TOPO_Rudy_hs_style.zip).
3. Run `python tools/update_rudy_style.py <downloaded.zip> --source-url <URL>`.
   This validates in staging, updates the untouched upstream assets, rebuilds
   the maintained theme and updates provenance. Inspect the upstream Git diff
   separately from policy changes; remove obsolete unused assets if warranted.
4. Run `python -m pytest tests/test_rudy.py tests/test_viewer_tiles.py
   tests/test_tailscale_access.py` and `node tests/view_state.cjs`.
5. Render real trail/stream scenes at z13–17, compare the upstream and maintained
   themes, check Chinese labels, symbols and layer switching, then restart the
   app. Commit upstream refresh separately from any required policy adaptation.

To adjust only enhancements, edit the policy and run
`python -m mapwalker.rudy_style`; never hand-edit the generated XML.
Rollback by restoring the previous tracked theme/assets and previous map file,
then restart. Existing tiles cannot leak across versions because the content key
changes. Save the previous map before running an update if rollback is needed.

## Attribution and licenses

Rudy / MOI.OSM Taiwan TOPO: https://rudymap.tw/ and
https://github.com/alpha-rudy/taiwan-topo.
Modified style reference: https://github.com/poi890poi/tw_mapsources/blob/master/mapstyles/bochengsiong.xml.
Theme based on Elevate by Tobias Kühn / OpenAndroMaps. Theme and modifications
are **CC BY-NC-SA 3.0**; preserve `upstream/License.txt`, including separate
resource licenses. Map data credits include OpenStreetMap (ODbL) and the sources
documented by Rudy. MapsforgeSrv is GPL-3.0; it is downloaded separately from
https://github.com/telemaxx/mapsforgesrv/releases/tag/v0.30.0.0.

## Change impact and evidence

Type: new viewer feature plus style maintenance. Main risks: Mapsforge theme
compatibility, missing resources, stale pixels after update, renderer failure,
and accidentally mixing modern rendering into historical analysis. Mitigations:
current upstream predicates/assets, tested deterministic regeneration, content
versioned disk cache, loopback-only renderer, and dedicated viewer routes outside
the detection source registry. Existing historical/NLSC caches, jobs, masks,
coordinates, findings and access policies retain their owners.

`evidence/rudy/viewer.png` shows real rendered Rudy imagery in the viewer.
Rendering verifies compatibility and visual output, not trail completeness,
position accuracy, or hiking safety.
