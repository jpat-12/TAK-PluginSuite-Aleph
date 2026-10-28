# Candidate open datasets — for Jon to choose from

**Proposal only. Nothing here is implemented.** Each entry would be a new layer (or a new source
for an existing layer) in `service/aleph_tak/layers/` + `sources.py`, a new option in
docs/API.md, and a checkbox in the three clients. Pick the ones you want and I'll build those.

Constraints every candidate was checked against:
- **Open licence that allows offline redistribution** inside a data package (no Google, no
  "view-only" terms). Public domain or CC BY / ODbL with attribution in `ATTRIBUTION.txt`.
- **No GDAL on the server.** Sources that are only FileGDB / shapefile / S-57 need either an
  ArcGIS REST / OGC API endpoint we can query by bbox as GeoJSON, or a pure-Python reader. The
  *Access* column says which.
- **Useful to a CAP aircrew or ground team** (search planning, flight safety, navigation).

## Tier 1 — highest value for CAP search & rescue

| # | Dataset | What it adds | Package output | Licence | Access (no GDAL) | Effort |
|---|---|---|---|---|---|---|
| 1 | **FAA VFR Sectional + Terminal Area charts** | The chart aircrews actually fly with, offline, under the same area | MBTiles (like imagery) | US Gov work, public domain | GeoTIFF zips from FAA Digital Products, 56-day cycle; tile with the existing COG/tiling code (needs a TIFF reader for LZW/deflate — Pillow can, check per chart) | M |
| 2 | **CAP grid / USNG-MGRS grid overlay** | Search grid lines + labels over the area (CAP grids are sectional-based 15′×15′, quartered) | KML/KMZ | Derived — no third-party data | Generated from the area's bbox | S |
| 3 | **FAA Digital Obstacle File (DOF)** | Towers, stacks, wind turbines with AGL/MSL heights — low-level flight safety | KML points (+ CoT optional) | Public domain | CSV from FAA, 56-day cycle; filter by bbox | S |
| 4 | **Contours from our own elevation** | Topo contour lines without a new source | KML lines | Derived from AWS Terrain Tiles | Marching squares over the DTED grid already fetched | S |
| 5 | **USGS National Hydrography (NHD → 3DHP)** | Named streams, intermittent drainages, springs — far denser than OSM in rural areas (lost persons follow drainages) | KML/GeoJSON (joins the OSM style) | Public domain | The National Map ArcGIS REST, query by envelope → GeoJSON. USGS is migrating NHD to 3DHP; target whichever is live | M |
| 6 | **USFS trails & roads (incl. MVUM)** | Official National Forest trails/roads with names, numbers and allowed use | KML lines | Public domain | USFS EDW ArcGIS REST by bbox | S |
| 7 | **Land cover: Annual NLCD (US, 30 m) or ESA WorldCover (global, 10 m)** | Forest / scrub / open / water / developed — drives probability-of-detection from the air and lost-person behaviour | MBTiles (classified colour) + legend | NLCD public domain; WorldCover CC BY 4.0 | NLCD: MRLC WMS/WCS; WorldCover: COGs on AWS | M |

## Tier 2 — useful, lower priority or more caveats

| # | Dataset | What it adds | Package output | Licence | Access (no GDAL) | Effort |
|---|---|---|---|---|---|---|
| 8 | **FAA airports, heliports, landing facilities (NASR)** | Helipads/strips near the search area, with elevation and runway info | KML points | Public domain | NASR 28-day CSV subscription | S |
| 9 | **PAD-US (protected areas / land ownership)** | Who owns the land (NPS, USFS, BLM, state, private) — access and jurisdiction | KML polygons | Public domain | USGS ArcGIS REST by bbox | S |
| 10 | **National Address Database (US DOT) / OpenAddresses** | Offline address points; improves point lookup's nearest address | GeoJSON + KML | NAD public domain; OpenAddresses per-source (mostly open, some CC BY) | NAD: bulk CSV (large — would need a pre-built index); OpenAddresses: per-county files | L |
| 11 | **Building footprints: Microsoft Global ML Buildings or Overture buildings** | Fills rural gaps in OSM buildings | Merged into OSM buildings | ODbL (both) — same terms as OSM | Microsoft: per-quadkey GeoJSONL; Overture: GeoParquet on S3 (needs a Parquet reader, e.g. pyarrow) | M |
| 12 | **Sentinel-2 L2A recent imagery (10 m)** | Imagery from the last weeks, not NAIP's 2–3-year cycle — post-flood/fire change at a glance (pairs well with the new Compare slider) | MBTiles | Copernicus free & open (attribution) | Element84 Earth Search STAC + COGs on AWS; needs cloud filtering and a COG reader | L |
| 13 | **HIFLD Next infrastructure** (hospitals, fire/EMS, law enforcement, cell towers…) | Where to send a found subject; staging points | KML points | Mixed per layer; community-maintained | HIFLD Open went offline Aug 2025; HIFLD Next and the DataLumos archive host the old layers, and many layers live at their original agencies again. Check each layer's licence before adopting it | M |
| 14 | **FEMA National Flood Hazard Layer** | Flood zones for water-rescue and disaster tasks | KML polygons | Public domain | FEMA ArcGIS REST by bbox | S |
| 15 | **Copernicus DEM GLO-30** | Second elevation source outside the US / cross-check | DTED/GeoTIFF (existing writers) | Free & open (GLO-30 Public; some countries withheld) | COGs on AWS (`copernicus-dem-30m`); needs a COG reader | M |

## Considered and not recommended

- **NOAA ENC nautical charts.** Great for lake and coastal searches, but S-57 needs GDAL. Revisit
  only if a pre-rendered NOAA tile service fits the licence.
- **Live weather / radar (NWS, NEXRAD).** Live data doesn't belong in an offline package; better
  as a live CloudTAK overlay.
- **EOX Sentinel-2 cloudless mosaics after 2016.** CC BY-NC-SA. Non-commercial terms are a poor
  fit to bake into redistributable packages.
- **Anything Google/Bing/Esri World Imagery.** Their terms forbid offline caching, which is the
  plan's main blocker.

## Suggested starting set

**1 (sectionals), 2 (CAP grid), 3 (obstacles), 4 (contours)**: high value for aircrews, all
public domain or derived, and three of the four are small. Then **5 (NHD)** and **7 (land cover)**
for ground-search planning.

Sources checked (Oct 2026): FAA Digital Products — VFR raster charts; Copernicus DEM on the AWS
Open Data Registry; Overture Maps FAQ (ODbL for OSM-derived themes); NAPSG / Data Rescue Project
on the HIFLD Open shutdown and HIFLD Next.
