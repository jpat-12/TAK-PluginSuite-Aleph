"""Open-data source adapters — the replacements for Aleph's Google endpoints.

Every source here is public-domain or openly licensed, and each carries the attribution line
that ends up in the package's ATTRIBUTION.txt. Upstream Aleph used Google Maps tiles, Street
View and Google Earth meshes; bulk/offline caching of those breaks Google's terms, so none of
them survive in this fork (plan: "Blocker: replace the Google sources").
"""

import math
from urllib.parse import urlencode

from .core.geo import MERCATOR_RADIUS

# Built-in imagery a capture can choose from (options.imagery_source). Each one is public domain or
# openly licensed for offline use; `description`/`resolution`/`updated` are shown to the user
# before they capture. Admin-defined sources (settings imagery.extra_sources, e.g. a state's
# orthoimagery) and the legacy single custom source are added by imagery_sources().
IMAGERY = {
    # Native ~0.6 m, refreshed every 2–3 years, contiguous US only. Served as an ArcGIS
    # ImageServer (no tile cache), so each 256 px tile is an exportImage request for its
    # Web Mercator bounds. The USGS *tiled* imagery cache stops at z16, too coarse for SAR.
    "usgs-naip": dict(
        name="USGS NAIP aerial",
        kind="arcgis-export",
        url="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage",
        attribution="Imagery: USDA National Agriculture Imagery Program (NAIP), via USGS The National Map. Public domain.",
        max_zoom=18,
        coverage="Contiguous United States",
        resolution="0.6–1 m",
        updated="Flown every 2–3 years",
        licence="Public domain",
        description="Aerial photos flown for USDA. The sharpest free imagery that covers the whole "
                    "lower 48; rendered on request, so it's the slowest to capture.",
    ),
    # The same NAIP-based pictures, pre-cut into tiles: much faster, but only to z16 (~2 m on screen).
    "usgs-imagery-only": dict(
        name="USGS Imagery Only (cached)",
        kind="xyz",
        url="https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        attribution="Imagery: USGS The National Map — Imagery Only base map (NAIP and other public-domain sources). Public domain.",
        max_zoom=16,
        coverage="United States",
        resolution="~2 m at its z16 limit",
        updated="Follows NAIP, 2–3 years",
        licence="Public domain",
        description="USGS's pre-tiled imagery base map. Captures much faster than NAIP and covers "
                    "Alaska/Hawaii/territories, but stops at z16 — less detail.",
    ),
    # EOX's cloud-free Sentinel-2 mosaic. Only the 2016 edition is CC BY; later years are
    # CC BY-NC-SA, which can't go into redistributable packages, so they're not offered.
    "eox-s2cloudless-2016": dict(
        name="Sentinel-2 cloudless 2016 (EOX)",
        kind="xyz",
        url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg",
        attribution="Sentinel-2 cloudless — https://s2maps.eu by EOX IT Services GmbH "
                    "(contains modified Copernicus Sentinel data 2016), CC BY 4.0.",
        max_zoom=14,
        coverage="Worldwide",
        resolution="10 m",
        updated="2016 mosaic",
        licence="CC BY 4.0",
        description="Cloud-free satellite mosaic of the whole world. Coarse (10 m) and from 2016, but "
                    "it works anywhere — use it outside the US or for large overview captures.",
    ),
}
DEFAULT_IMAGERY = "usgs-naip"
KINDS = ("xyz", "arcgis-export")

# Terrarium-encoded PNGs from the same AWS Terrain Tiles bucket Aleph used (as GeoTIFF).
# PNG decodes with Pillow alone, so the service needs no TIFF decoder for elevation.
TERRAIN_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TERRAIN_ATTRIBUTION = ("Elevation: AWS Terrain Tiles (Mapzen/Tilezen) — sources incl. USGS 3DEP, SRTM, GMTED2010, "
                       "ETOPO1; see https://github.com/tilezen/joerd/blob/master/docs/attribution.md")
OSM_ATTRIBUTION = "Map data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright), via Geofabrik."
MAPILLARY_ATTRIBUTION = "Street-level photos © Mapillary contributors, CC BY-SA 4.0 (https://www.mapillary.com)."
MAPILLARY_GRAPH = "https://graph.mapillary.com"


def _admin_source(raw, fallback_name):
    """An admin-entered source (extra_sources entry or the legacy custom slot), normalised."""
    if raw.get("kind", "xyz") not in KINDS:
        raise ValueError(f"{fallback_name}: kind must be one of {', '.join(KINDS)}.")
    return dict(name=raw.get("name") or fallback_name, kind=raw.get("kind", "xyz"), url=raw["url"],
                attribution=raw.get("attribution") or f"Imagery: {raw.get('name') or fallback_name} (licensed source).",
                max_zoom=int(raw.get("max_zoom", 19)), coverage=raw.get("coverage") or "Per licence",
                resolution=raw.get("resolution") or "", updated=raw.get("updated") or "",
                licence=raw.get("licence") or "Per licence", description=raw.get("description") or "Added by the server admin.")


def imagery_sources(settings):
    """Every source a capture may use on this server, id → source, built-ins first."""
    imagery = settings["imagery"]
    result = dict(IMAGERY)
    custom = imagery.get("custom") or {}
    if custom.get("url"):
        result["custom"] = _admin_source(dict(custom, name=custom.get("name") or "Custom imagery"), "Custom imagery")
    for i, raw in enumerate(imagery.get("extra_sources") or []):
        if isinstance(raw, dict) and raw.get("url"):
            result[str(raw.get("id") or f"extra-{i + 1}")] = _admin_source(raw, f"Extra imagery {i + 1}")
    return result


def imagery_source(settings, source_id=None):
    """The source a capture uses: the requested one, else the server's default."""
    available = imagery_sources(settings)
    chosen = source_id or settings["imagery"]["source"]
    if chosen == "custom" and "custom" not in available:
        raise ValueError("Custom imagery is selected but no URL is configured.")
    if chosen not in available:
        raise ValueError(f"Unknown imagery source: {chosen}")
    return available[chosen]


def tile_bounds_3857(x, y, zoom):
    size = 2 * math.pi * MERCATOR_RADIUS / 2**zoom
    half = math.pi * MERCATOR_RADIUS
    return -half + x * size, half - (y + 1) * size, -half + (x + 1) * size, half - y * size


def imagery_url(source, x, y, zoom):
    if source["kind"] == "xyz":
        return source["url"].format(z=zoom, x=x, y=y)
    if source["kind"] == "arcgis-export":
        bbox = ",".join(f"{v:.3f}" for v in tile_bounds_3857(x, y, zoom))
        return source["url"] + "?" + urlencode(dict(bbox=bbox, bboxSR=3857, imageSR=3857, size="256,256",
                                                    format="jpg", f="image"))
    raise ValueError(f"Unknown imagery source kind: {source['kind']}")
