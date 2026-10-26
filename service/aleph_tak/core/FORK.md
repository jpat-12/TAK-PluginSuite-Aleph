# Fork record — `aleph_tak/core/`

Forked from [Belluxx/Aleph](https://github.com/Belluxx/Aleph) at commit
`ad68fc4a3c60fd7af3969597ef0ba886c63b0a40` (2026-10-22), MIT licence — see `LICENSE-ALEPH`,
which must stay with this code.

**We fork once and own it; we don't track upstream.** Aleph's author ignores backward
compatibility by design (its AGENTS.md: "Completely ignore backward compatibility"), so pulling
upstream changes would be a rewrite each time.

## Kept (unchanged unless noted)

| File | Why it's here |
|---|---|
| `geo.py` | Polygon validation, Web Mercator tile grids, segment clipping — the planning math every layer uses. |
| `common.py` | Retrying HTTP client with cancellation, atomic file writes. **Changed:** identifies as `AlephTAK/1` instead of spoofing a Safari user agent (we only call open-data services, which ask for an honest UA). |
| `satellite.py` | Pure-Python lossless Cloud-Optimized GeoTIFF writer (no GDAL). **Changed:** output name is a parameter and the PNG copy is opt-in. Used for the optional `geotiff` imagery format. |
| `pbf.py`, `osm.py` | Geofabrik region lookup and the bundled OSM PBF reader. Unchanged. |
| `places.py` | Photon geocoder client (point lookup's "nearest address"). Unchanged; the endpoint is configurable. |

## Dropped, and why

| Upstream module | Reason |
|---|---|
| `streetview.py`, `routes.py`, `quick.py` | Google Street View internal APIs — undocumented, and Google's terms bar caching. Replaced by Mapillary (`layers/photos.py`). |
| `mesh.py` | Reverse-engineered Google Earth 3D mesh — no licence. Dropped from v1 (plan). |
| Google Maps tiles (in `capture.py`) | Terms bar bulk/offline use. Replaced by USGS NAIP (`sources.py`). |
| `terrain.py` | Merged AWS Terrain Tiles *GeoTIFFs*; we fetch the same bucket's Terrarium PNGs instead, which decode with Pillow, so no TIFF decoder is needed. Same data. |
| `capture.py`, `dashboard.py`, `cli.py`, `layers.py`, `web/` | Aleph's CLI/dashboard orchestration; replaced by the job service (`jobs.py`, `app.py`) and the TAK clients. |

Aleph's own PBF tests came along as `service/tests/test_core_pbf.py`.
