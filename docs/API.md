# Aleph capture service — API v1

The contract between the service (`service/aleph_tak/app.py`) and every client: the ATAK plugin
talks to it directly, the CloudTAK plugin through its server half
(`cloudtak/server/plugin-aleph.ts`), which relays the same JSON. `service/tests/test_api.py`
pins this behaviour.

Base URL: `https://aleph.<infra-TAK fqdn>` (Caddy → `127.0.0.1:8781`). All bodies are JSON.

## Versioning

`GET /api/v1/info` → `"api": 1`. The number changes only on breaking changes; clients compare it
with the major they support and refuse to proceed otherwise (`Models.SUPPORTED_API` in ATAK,
`SUPPORTED_API` in `cloudtak/plugin/lib/client.ts`). Additive fields don't bump it, and clients
must ignore fields they don't know.

## Authentication

| Caller | How | Identity |
|---|---|---|
| ATAK / any device | `Authorization: Bearer alt_<id>_<secret>` — a **client** token from the admin page or `aleph-tak create-token NAME` | the token's name |
| A server that has its own users (CloudTAK's route) | **proxy** token + `X-Aleph-User: <user>` per request | `<token name>:<user>` |
| Browser / map library | signed link: `?exp=<unix>&sig=<hmac>` — returned inside job records | none (the link is the grant) |

Users only ever see their own jobs. Signed links are scoped to one job and one kind
(`package`, `tiles`, `layers`, `photos`) and expire after `signed_url_hours` (default 12).
Errors are `{"error": "message for the operator"}` with a 4xx/5xx status.

## Endpoints

### `GET /api/v1/info` — public
```json
{"service": "aleph-tak", "version": "0.1.0", "api": 1,
 "layers": ["imagery", "elevation", "osm"],            // what this server can capture now
 "max_area_km2": 25,
 "imagery": {"name": "USGS NAIP aerial", "coverage": "Contiguous United States", "max_zoom": 18, …},   // the default source
 "imagery_sources": [                                  // every source a capture may pick (0.1.4+)
   {"id": "usgs-naip", "default": true, "name": "USGS NAIP aerial", "coverage": "Contiguous United States",
    "max_zoom": 18, "resolution": "0.6–1 m", "updated": "Flown every 2–3 years", "licence": "Public domain",
    "description": "Aerial photos flown for USDA. …"},
   {"id": "usgs-imagery-only", …}, {"id": "eox-s2cloudless-2016", …}, …admin-added sources],
 "default_imagery_zoom": 17, "dted_level": 2, "job_ttl_hours": 72, "point_lookup": true}
```
`photos` appears only when an admin has set a Mapillary token. Built-in sources: USGS NAIP
(0.6–1 m, lower 48, slow), USGS Imagery Only (cached NAIP, ≤ z16, fast), Sentinel-2 cloudless
2016 by EOX (10 m, worldwide, ≤ z14, CC BY). Admins add more (e.g. state orthoimagery) in
/admin → *Extra imagery sources*; only sources licensed for offline use belong there.

### Capture request (body of `/estimate` and `/jobs`)
```json
{"area": {"type": "Polygon", "coordinates": [[[-89.62, 39.70], [-89.6035, 39.70], [-89.6035, 39.712], [-89.62, 39.712], [-89.62, 39.70]]]},
 "layers": ["imagery", "elevation", "osm"],
 "name": "Lake Springfield sector 3",
 "options": {"imagery_source": "usgs-naip", "imagery_zoom": 17, "dted_level": 2, "imagery_formats": ["mbtiles"]}}
```
- `area`: GeoJSON Polygon or Feature (outer ring used; ≤ 1000 vertices, non-self-intersecting),
  or a `[west, south, east, north]` bbox. Must be ≤ `max_area_km2`; its bounding box ≤ 4× that.
- `layers`: subset of `info.layers` (default: all available). `options` are all optional:
  `imagery_source` an `info.imagery_sources[].id` (default: the server's default),
  `imagery_zoom` 12…that source's `max_zoom` (400 if finer), `dted_level` 1|2, `imagery_formats` adds `"geotiff"` (lossless COG, ~8× bigger).

### `POST /api/v1/estimate`
`{"area_km2": 1.883, "bytes": 1338323, "seconds": 65, "allowed": true, "max_area_km2": 25, "layers": {"imagery": {"tiles": 49, "zoom": 17, "source": "USGS NAIP aerial", "bytes": …, "seconds": …}, …}}`
Rough (±30%); clients show it before submitting.

### `POST /api/v1/jobs` → 201 + job record
429 if the caller already has 3 captures queued/running.

### `GET /api/v1/jobs` → `{"jobs": [job, …]}` (newest first) · `GET /api/v1/jobs/{id}` → job

### `DELETE /api/v1/jobs/{id}` — cancels if queued/running (`{"state": "cancelling"}`), else deletes.

### `POST /api/v1/jobs/{id}/retry` — re-queues a finished job; tiles already on disk are reused, so it only fetches gaps. 409 while in progress.

### Job record
```json
{"id": "j28b19ff58e1c", "name": "Lake Springfield test", "owner": "CAP-IL-001", "state": "complete",
 "created_at": "…", "updated_at": "…", "expires_at": "…", "area": {…}, "area_km2": 1.883,
 "layers": ["imagery", "elevation", "osm"], "options": {…}, "percent": 100,
 "progress": {"imagery": {"state": "complete", "phase": "Writing MBTiles", "done": 49, "total": 49, "stats": {…}}, …},
 "warnings": [], "error": null,
 "package": {"filename": "Lake-Springfield-test.zip", "bytes": 1261776, "sha256": "b55f…", "uid": "…"},
 "links": {"package": "https://…/package?exp=…&sig=…",
           "tiles": "https://…/tiles/{z}/{x}/{y}?exp=…&sig=…", "tiles_info": {"min_zoom": 11, "max_zoom": 17, "bounds": [w, s, e, n]},
           "osm": "https://…/layers/osm?…", "photos": "…", "photo_image": "https://…/photos/{id}?…", "area": "…"}}
```
`state`: `queued → running → complete | failed | cancelled`. A layer can fail while the job
completes (its `progress[layer].state == "failed"` with an `error`); the job fails only if every
layer failed. `links` exists only when `complete`.

**Tiles that fail to download.** Each layer retries failed tiles once automatically (after ~5 s,
at half the concurrency; `phase` reads "Retrying N failed … tiles" meanwhile). Imagery tiles that
still fail leave the layer `complete` with blank gaps, a warning, and
`progress.imagery.stats.failed_tiles > 0`; clients then offer **Retry missing tiles**, which is just
`POST …/retry` (it refetches only the gaps). Elevation tolerates no failed tiles: the layer fails
instead, and Retry applies the same way. `failed_tiles` is additive — absent on jobs from ≤ 0.1.3.

### `GET /api/v1/jobs/{id}/package` — the TAK data package
Bearer (ATAK) **or** signed link (browser). Supports `Range` / `If-Range` (ETag = SHA-256) for
resumable downloads; `X-Content-SHA256` header. Layout: [`PACKAGE-FORMAT`](#package-format).

### Signed browser resources
- `GET /jobs/{id}/tiles/{z}/{x}/{y}` — imagery tile (JPEG, or PNG where partially empty); `204` = no tile.
- `GET /jobs/{id}/layers/{osm|photos|area}` — GeoJSON.
- `GET /jobs/{id}/photos/{photoId}` — a captured street-level image.
All send `Access-Control-Allow-Origin: *` (the signature is the authorization).

### `GET /api/v1/point?lat=&lon=`
`{"lat", "lon", "elevation_m", "address": {"label", "distance_m", …} | null,
 "street_address": {"label": "413 North 5th Street, Springfield, Illinois 62702", "exact": true, "distance_m",
                    "housenumber", "street", "city", "state", "postcode", "country"} | null, "photos": [{"id", "distance_m", "thumb_url", "image_url", "captured_at"}] | null, "errors": {part: message}, "attribution": [...]}`
Each part degrades on its own; `photos` is `null` when the server has no Mapillary token.
`address` is the nearest named place; `street_address` (0.1.4+) the nearest house address from
OpenStreetMap, or just the street (`exact: false`) when no house number is mapped nearby.

## Package format

A TAK mission package (v2 manifest) — the one artefact every client consumes:

| Path | Imported by TAK? | Content |
|---|---|---|
| `MANIFEST/manifest.xml` | — | contents list; photo files linked to their marker by `uid` |
| `imagery/<name>.mbtiles` | yes | JPEG pyramid, capture zoom down 6 levels (ATAK reads MBTiles natively) |
| `imagery/<name>.tif` | yes (if requested) | lossless RGBA COG, EPSG:3857 |
| `elevation/<name>-dted.zip` | **no** (`ignore="true"`) | `DTED/w090/n39.dt2`… — merged by the ATAK plugin, filling voids only, because a capture's cells are void outside the area and must never replace a device's complete cells |
| `elevation/<name>-elevation.tif` | no | Float32 GeoTIFF, EPSG:4326, nodata −32767 (GIS use) |
| `osm/<name>.kmz` | yes | one folder per layer: roads, trails, buildings, water, power lines, airfields/helipads, places |
| `photos/<uid>.cot` + `photos/<uid>/<id>.jpg` | yes | `b-i-x-i` (Quick Pic) markers with the photo attached; CC BY-SA credit in remarks |
| `aleph.json`, `ATTRIBUTION.txt` | no | provenance: sources, dates, licences, settings |
