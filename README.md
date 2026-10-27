# Aleph for TAK

**Draw a search area in ATAK, WinTAK or CloudTAK and get back an offline TAK data package of it** —
open-data aerial imagery, DTED elevation, OSM roads/trails/buildings/water/power lines, and
street-level photos — captured by one service on your infra-TAK server, instead of each team
hand-assembling imagery, DTED and KML from five websites before a sortie, or relying on
Google-scraping tools whose terms forbid offline use.

Built from [Belluxx/Aleph](https://github.com/Belluxx/Aleph) (MIT) with every Google source
replaced by open data. Plan: [`docs/Aleph for TAK — Plugin Plan.pdf`](docs/).

## The key idea

**The server does all the work; the data package is the contract.** One Python service tiles,
merges and writes GeoTIFF/DTED/MBTiles/KMZ once. ATAK and CloudTAK are thin clients that send an
area and a layer list and get back the *same* zip — which ATAK (and WinTAK, and TAK Server Data
Sync) already know how to import. So a new client is a few hundred lines, never a
reimplementation of the geo pipeline, and anything new (a layer, a source) lands in one place.

The second idea is how it lives on infra-TAK: **it never edits infra-TAK's code.** infra-TAK's
Update Now (`git checkout --force`) erases app.py patches, so Aleph runs as its own service and
attaches to the console at runtime through an import hook — verified on every infra-TAK
release from v0.1.0 to v10.2.30 ([details](docs/INFRATAK-COMPATIBILITY.md)).

## Install (infra-TAK host, as root)

```bash
git clone https://github.com/jpat-12/TAK-PluginSuite-Aleph.git
sudo bash TAK-PluginSuite-Aleph/infratak/install.sh --cloudtak   # drop --cloudtak if you don't run CloudTAK
```

That's the whole install: service on `127.0.0.1:8781`, `https://aleph.<your fqdn>` in Caddy, the
**Aleph for TAK** card and sidebar link in the infra-TAK console, and (with `--cloudtak`) the
CloudTAK plugin wired up and rebuilt. Re-run the same command to update. Remove with
`sudo bash /opt/aleph-tak/bin/uninstall.sh [--purge] [--cloudtak]`.

Then: console → **Aleph** → **Open Aleph admin** → create a **client** token per ATAK user →
they paste the server URL + token into the ATAK plugin.

## Build the clients

| Client | Command | Output |
|---|---|---|
| ATAK (5.6 SDK) | `cp atak/local.properties.example atak/local.properties` (edit paths), then `cd atak && JAVA_HOME="C:/Program Files/Android/Android Studio/jbr" ./gradlew assembleCivDebug testCivDebugUnitTest` | `atak/app/build/outputs/apk/civ/debug/ATAK-Plugin-Aleph-<ver>-ATAK-5.6-civ-debug.apk` |
| WinTAK (5.6) | `dotnet build wintak/AlephWinTak -c Release` (needs WinTAK installed); install: elevated `.\wintak\install.ps1`; tests: `dotnet test wintak/AlephWinTak.Tests` | `wintak/AlephWinTak/bin/Release/AlephWinTak.dll` → `<WinTAK>\Plugins\` |
| CloudTAK (13.14 and 13.1xx layouts) | compiled inside CloudTAK by `cloudtak/install.sh`; check without deploying: `CLOUDTAK_DIR=/path/to/CloudTAK node cloudtak/check-in-cloudtak.mjs` | baked into the CloudTAK API image |
| Service | `cd service && python -m unittest discover -s tests -t .` | runs from source; `install.sh` sets up its venv |

## Layout

```
VERSION                          one version for service, CloudTAK plugin and APK (PATCH-bump per build)
docs/
  API.md                         the /api/v1 contract + package format — every client builds against this
  INFRATAK-COMPATIBILITY.md      why/how it runs on any infra-TAK version; the every-release test
  VERIFY.md                      release smoke test (automated + field steps)
  Aleph for TAK — Plugin Plan.pdf the plan this implements
service/                         the capture service (Python ≥3.10, Flask + waitress, no GDAL)
  aleph_tak/
    app.py                       HTTP API: auth, signed links, Range downloads, CORS
    admin.py                     /admin: tokens, settings, all jobs (console SSO or local password)
    jobs.py                      job store (JSON per job), worker pool, expiry janitor — the canonical job state
    area.py                      area/layer validation and the pre-submit size estimate
    sources.py                   open-data endpoints + attribution (the Google replacements)
    net.py                       per-tile fault-tolerant downloading (one USGS 502 ≠ lost layer)
    point.py                     point lookup: elevation, nearest address, nearby photos
    auth.py                      bearer tokens (hashed), proxy users, HMAC signed URLs, SSO signature
    config.py                    settings + secrets in the data dir, forward-compatible loading
    layers/                      imagery · elevation · osm · photos — each resumable, run(ctx) → result
    formats/                     dted · geotiff · mbtiles · kml · cot · datapackage writers (byte-exact, tested)
    core/                        forked Aleph (geo, tiles, COG writer, OSM PBF reader) — see core/FORK.md
  tests/                         50 tests incl. formats, API contract, live-source fakes, infra-TAK × every release
infratak/                        infra-TAK integration (never edits infra-TAK's git-tracked files)
  install.sh / uninstall.sh      one-command install/update/remove, any infra-TAK version
  aleph_infratak.py              console hook: routes, card, sidebar, Caddy re-add — each feature-detected
  aleph_infratak_boot.py, .pth   loads the hook when gunicorn imports the console's app
  aleph_caddy.py                 the Caddy site block, below infra-TAK's user-blocks marker
  heal.sh, systemd/              service unit + path unit that re-applies integration after infra-TAK rewrites
cloudtak/                        CloudTAK plugin
  plugin/                        web half → api/web/plugins/aleph/ (Vue 3 panel, map previews, point lookup)
  server/plugin-aleph.ts         server half → api/routes/: relays JSON with a server-side proxy token
  install.sh                     copies both halves, merges ALEPH_URL/TOKEN into api/.env, rebuilds
  check-in-cloudtak.mjs          runs CloudTAK's own lint + vue-tsc against the plugin
wintak/                          WinTAK plugin (C#, .NET Framework 4.8, WinTAK 5.6 SDK = the installed WinTAK's DLLs)
  AlephWinTak/
    AlephModule.cs, AlephButton.cs   MEF/Prism entry + Home → Tools ribbon button
    AlephDockPane.cs                 the pane (MEF imports: import manager, WinTAK's area pickers, map, DTED registry)
    AlephViewModel.cs, AlephView.xaml  the flow: connect → area → layers → estimate → capture → download & import
    Core/                            pure logic, no WinTAK: AlephClient (HTTP + resumable SHA-256 download),
                                     Models, AreaMath, DtedCell/DtedInstaller (fill-voids merge), AlephSettings (DPAPI token)
  AlephWinTak.Tests/                 .NET 8 xunit tests of Core/ against the same service-written fixture as ATAK
  install.ps1                        elevated install/remove into <WinTAK>\Plugins
atak/                            ATAK plugin (Java, ATAK-CIV 5.6 SDK)
  app/src/main/java/com/atakmap/android/aleph/
    AlephDropDownReceiver.java   the panel (UI only; work goes to the worker thread)
    AlephMapComponent.java       owns config, client, single worker executor
    api/                         AlephClient (HTTP), AlephConfig (https-only URL), Models (JSON at the boundary)
    area/                        AreaPicker (tap a shape / point / map view), AreaMath (pure, tested)
    download/                    resumable SHA-256-verified download, DTED merge, ATAK import handoff
  app/src/test/                  JVM tests; resources/ holds a package the Python service wrote
```

## Status

| Feature (plan section) | State | Notes |
|---|---|---|
| Phase 0 — open-data sources replace Google | ✅ | Live capture of 1.88 km² at Lake Springfield, IL: 49 NAIP tiles (0.92 m), DTED2 cell 170–178 m, 239 OSM features, 1.26 MB package in 83 s. **Gate met.** |
| Imagery: USGS NAIP → MBTiles (+ optional COG) | ✅ | Pluggable: admin can set a custom XYZ/ArcGIS source CAP is licensed for |
| Elevation: AWS Terrain Tiles → DTED1/2 + GeoTIFF | ✅ | Byte-exact DTED writer, tested both in Python and against the Java reader |
| OSM via Geofabrik → KMZ + GeoJSON | ✅ | Ways and named POIs; lines clipped to the area |
| OSM multipolygon relations (big lakes with islands, large landuse) | ⬜ Deferred | v1 reads closed ways only |
| Street-level photos (Mapillary) | 🔧 Hook in place | Code done and unit-tested with fakes; **needs a Mapillary token** (admin page) to go live — not yet run against the real API |
| USGS 3DEP 1 m elevation | ⬜ Deferred | Terrain Tiles already include 3DEP 1/3″ in the US |
| 3D mesh | ⬜ Dropped (plan) | No licensed source |
| Phase 1 — job API, auth, estimate, package | ✅ | 50 service tests; resumable Range downloads; per-user jobs; 72 h expiry |
| infra-TAK integration on any version | ✅ | Hook verified on all 250 infra-TAK releases (v0.1.0 → v10.2.30); Caddy + heal tested locally. **Full `install.sh` not yet run on a real host** |
| Phase 2 — CloudTAK plugin | 🔧 Built | Passes CloudTAK 13.14.1's lint + `vue-tsc`; not yet run in a live CloudTAK |
| Phase 3 — ATAK plugin | 🔧 Built | APK builds and its unit tests pass against the 5.6 SDK; needs the airplane-mode device test (docs/VERIFY.md) |
| Phase 4 — WinTAK plugin | 🔧 Built | Builds against the installed WinTAK 5.6.0.151 with 0 warnings; MEF exports verified; 15 Core tests pass. Uses WinTAK's own rectangle / polygon / existing-shape pickers and import pipeline. Not yet loaded in a running WinTAK |
| TAK Server Data Sync push, field node, AI terrain brief | ⬜ Phase 5 | Decisions needed (below) |
| ATAK token onboarding by QR | ⬜ Deferred | Paste URL + token for now |

## Deliberate deviations (don't "fix" these back)

- **MBTiles is the default imagery format, not the plan's COG.** ATAK 5.6 reads MBTiles natively
  (`MbTilesFileType` in the SDK) and JPEG tiles are ~6–8× smaller than Aleph's lossless COG. The
  COG is still available (`imagery_formats: ["geotiff"]`).
- **The DTED zip is `ignore="true"` in the package.** Capture cells are void outside the area; a
  generic import could replace a device's complete state-wide cell with a mostly-empty one. The
  ATAK plugin merges DTED itself and only ever fills voids.
- **Terrain comes from Terrarium PNGs, not the GeoTIFF tiles Aleph used** — same AWS bucket and
  data, but decodable with Pillow, so the service needs no GDAL/TIFF decoder anywhere.
- **The Aleph site is not behind Authentik forward_auth.** ATAK authenticates with Aleph bearer
  tokens, browsers with signed links, and /admin with the console's single sign-on; forward_auth
  would lock the phones out. Captures still never leave the server unauthenticated.
- **Capture previews in CloudTAK are plain MapLibre layers, not CoT** (against the CloudTAK
  plugin guide's default): thousands of OSM features pushed through the feature DB would be
  broadcast as CoT and swamp DataSync.
- **No app.py patching on infra-TAK** (unlike the sibling InfraTAK modules) — see the key idea.

## Decisions needed (from the plan)

| Question | What this build assumes until decided |
|---|---|
| Own plugin, or a module inside FeatureLink? | Own plugin (separate repo, APK, CloudTAK plugin) |
| Imagery CAP is licensed for beyond NAIP? | NAIP only; custom-source slot ready in admin settings |
| Host only on prod.ilwg.us, or also a field node? | Any infra-TAK host; a field node is just another install (pre-cached areas not built yet) |
| AI terrain brief? | Left out |

## Attribution

Capture code derived from Aleph © 2026 Belluxx (MIT, `service/aleph_tak/core/LICENSE-ALEPH`).
Every package carries `ATTRIBUTION.txt` for its sources: USDA NAIP via USGS (public domain), AWS
Terrain Tiles / Tilezen sources, © OpenStreetMap contributors (ODbL), Mapillary contributors
(CC BY-SA 4.0).
