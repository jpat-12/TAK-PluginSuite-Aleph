"""Open-data source adapters — the replacements for Aleph's Google endpoints.

Every source here is public-domain or openly licensed, and each carries the attribution line
that ends up in the package's ATTRIBUTION.txt. Upstream Aleph used Google Maps tiles, Street
View and Google Earth meshes; bulk/offline caching of those breaks Google's terms, so none of
them survive in this fork (plan: "Blocker: replace the Google sources").
"""

import math
from urllib.parse import urlencode

from .core.geo import MERCATOR_RADIUS

IMAGERY = {
    # Native ~0.6 m, refreshed every 2–3 years, contiguous US only. Served as an ArcGIS
    # ImageServer (no tile cache), so each 256 px tile is an exportImage request for its
    # Web Mercator bounds. The USGS *tiled* imagery cache stops at z16, too coarse for SAR.
    "usgs-naip": dict(
        name="USGS NAIP (public domain)",
        kind="arcgis-export",
        url="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage",
        attribution="Imagery: USDA National Agriculture Imagery Program (NAIP), via USGS The National Map. Public domain.",
        max_zoom=18,
        coverage="Contiguous United States",
    ),
}

# Terrarium-encoded PNGs from the same AWS Terrain Tiles bucket Aleph used (as GeoTIFF).
# PNG decodes with Pillow alone, so the service needs no TIFF decoder for elevation.
TERRAIN_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TERRAIN_ATTRIBUTION = ("Elevation: AWS Terrain Tiles (Mapzen/Tilezen) — sources incl. USGS 3DEP, SRTM, GMTED2010, "
                       "ETOPO1; see https://github.com/tilezen/joerd/blob/master/docs/attribution.md")
OSM_ATTRIBUTION = "Map data © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright), via Geofabrik."
MAPILLARY_ATTRIBUTION = "Street-level photos © Mapillary contributors, CC BY-SA 4.0 (https://www.mapillary.com)."
MAPILLARY_GRAPH = "https://graph.mapillary.com"


def imagery_source(settings):
    imagery = settings["imagery"]
    if imagery["source"] == "custom":
        custom = imagery["custom"]
        if not custom.get("url"):
            raise ValueError("Custom imagery is selected but no URL is configured.")
        return dict(name="Custom imagery", kind=custom.get("kind", "xyz"), url=custom["url"],
                    attribution=custom.get("attribution") or "Imagery: custom licensed source.",
                    max_zoom=int(custom.get("max_zoom", 19)), coverage="Per license")
    if imagery["source"] not in IMAGERY:
        raise ValueError(f"Unknown imagery source: {imagery['source']}")
    return IMAGERY[imagery["source"]]


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
