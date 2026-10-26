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
6. **Show** → NAIP imagery, OSM lines and the dashed outline appear over the basemap; CoT
   markers stay on top. Point lookup returns an elevation.
7. Download the package → it's a zip with `MANIFEST/manifest.xml`.

## ATAK (plan gate: package works with the device in airplane mode)

8. Install the APK → Aleph Capture → paste URL + token → **Save & connect** → "Connected".
9. Draw a rectangle with ATAK's shape tool → **Pick a shape** → tap it → estimate shows.
10. Capture → wait for complete → **Download & import** on Wi-Fi. Kill the network mid-download
    once: the retry resumes rather than restarting.
11. Airplane mode → the imagery (Overlay Manager → MBTiles), OSM KMZ and elevation (long-press
    → elevation reads a value inside the area) all still work. Elevation of an existing DTED cell
    outside the area is unchanged.

Record the ATAK/CloudTAK/infra-TAK versions you ran this on in the release notes.
