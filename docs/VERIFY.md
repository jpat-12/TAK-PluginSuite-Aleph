# Release smoke test

Run before tagging. Automated checks first, then the field steps no CI can do.

## Automated (any dev box)

```bash
cd service && python -m unittest discover -s tests -t .           # service, formats, installer pieces
INFRATAK_REPO=../../infra-TAK python -m unittest tests.test_infratak_hook   # console hook × infra-TAK versions
CLOUDTAK_DIR=/path/to/CloudTAK node ../cloudtak/check-in-cloudtak.mjs       # CloudTAK's own lint + vue-tsc
cd ../atak && ./gradlew assembleCivDebug testCivDebugUnitTest                # APK + DTED/JSON/area tests
```

## On an infra-TAK host

1. `sudo bash infratak/install.sh --cloudtak` → prints the public URL; `systemctl status aleph-tak` is active.
2. infra-TAK console shows the **Aleph for TAK** card and sidebar link → **Open Aleph admin** signs you in.
3. Admin → create a **client** token for a test callsign.
4. Click **Update Now** in infra-TAK (or `git checkout` another tag + restart) → the card and
   `https://aleph.<fqdn>/api/v1/info` still work.

## CloudTAK (plan gate: area → map layers in one browser flow)

5. Settings → Refresh App → menu → **Aleph Capture** → Draw box over a ~2 km² Illinois area →
   estimate shows → Capture → progress reaches **complete** in ~1–2 min.
6. Toggle **Imagery** → NAIP imagery and the dashed outline appear over the basemap; **OSM** adds
   the lines on top of the imagery (in either order); **Photos** adds the photo dots. CoT markers
   stay on top. Switching every dataset off removes the capture from the map. A legend appears
   bottom-left (above the GPS panel) listing only the datasets switched on, and only the OSM
   categories in the capture; its header collapses it. Point lookup returns an elevation and,
   in a town, a street address ("413 North 5th Street, Springfield, Illinois 62702 · 12 m away").
   Before capturing: each layer shows what it downloads and its estimated size; pick each imagery
   source in turn, capture a small area with it, and check the tiles come back (NAIP slowest; USGS
   Imagery Only stops at z16; Sentinel-2 cloudless at z14).
   **Compare** → the area becomes a slider: capture west of the divider, live basemap east of it.
   Drag the handle (or the panel's range) both ways, pan/rotate/pitch — the two halves stay
   aligned; the attribution still lists the capture's sources. Toggling a dataset while comparing
   keeps the divider where it was. **Compare** again puts the normal preview back.
   Tile trouble: stop the Aleph service for ~10 s while imagery is shown and pan → after a few
   seconds the plugin reloads the tiles once by itself; if they still fail, the card shows
   **Reload tiles** — start the service, press it, the imagery fills in. A capture whose imagery
   still had failed tiles after the service's own automatic retry shows **Retry N missing tiles**.
7. Download the package → it's a zip with `MANIFEST/manifest.xml`.

## ATAK (plan gate: package works with the device in airplane mode)

8. Install the APK → Aleph Capture → paste URL + token → **Save & connect** → "Connected".
9. Draw a rectangle with ATAK's shape tool → **Pick a shape** → tap it → estimate shows. Each
   layer shows a line on what it downloads and, once estimated, its size. Under Imagery, pick each
   source in turn: its description appears and the detail list ends at that source's limit
   (NAIP z18, USGS Imagery Only z16, Sentinel-2 cloudless z14).
10. Capture → wait for complete → **Download & import** on Wi-Fi. Kill the network mid-download
    once: the retry resumes rather than restarting.
11. Airplane mode → the imagery (Overlay Manager → MBTiles), OSM KMZ and elevation (long-press
    → elevation reads a value inside the area) all still work. Elevation of an existing DTED cell
    outside the area is unchanged.
12. Point lookup → tap a spot in a town → a street address with its distance, then "Near …".
    A capture whose imagery still had failed tiles shows **Retry N missing tiles**.

## WinTAK

13. `dotnet build wintak/AlephWinTak -c Release` and `dotnet test wintak/AlephWinTak.Tests`, then
    elevated `.\wintak\install.ps1` → restart WinTAK → Home → Tools → Aleph.
14. Repeat steps 8–12 in the pane: connect, pick an area with WinTAK's rectangle/polygon tools,
    check the layer lines, sizes and the imagery-source picker under Imagery, capture,
    **Download & import**, click a spot for point lookup.

Record the ATAK/WinTAK/CloudTAK/infra-TAK versions you ran this on in the release notes.
