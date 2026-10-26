"""Turn a client's area + layer choice into a validated request, and estimate what it will cost.

Clients send GeoJSON ([lon, lat], what every web map and TAK export speaks); Aleph's geometry
core works in (lat, lon). The conversion happens here, once, at the boundary.
"""

import math

from .core.geo import corners, extent, grid, measure, vertices

LAYERS = ("imagery", "elevation", "osm", "photos")

# Rough per-item package sizes, measured on Illinois NAIP / Terrarium / Geofabrik samples.
# They only drive the pre-submit estimate and the area cap, so being ~30% off is fine.
JPEG_TILE_BYTES = 18_000          # USGS NAIP export, 256 px, default JPEG quality
COG_TILE_BYTES = 150_000          # lossless RGBA deflate (Aleph's COG writer)
OVERVIEW_FACTOR = 4 / 3           # each overview level adds a quarter of the one below
DTED_POST_BYTES = 1.1             # 2-byte posts after zip, terrain compresses ~2:1
DTED_EMPTY_CELL_BYTES = 40_000    # a mostly-void 1°×1° cell, zipped
GEOTIFF_POST_BYTES = 2.4          # Float32 + deflate
OSM_BYTES_PER_KM2 = 60_000        # KMZ, small-town density; cities run several times higher
PHOTO_BYTES = 140_000             # Mapillary thumb_1024 JPEG


def parse_area(value):
    """GeoJSON Polygon/Feature, or a [west, south, east, north] bbox → Aleph (lat, lon) polygon."""
    if isinstance(value, dict) and value.get("type") == "Feature":
        value = value.get("geometry")
    if isinstance(value, list) and len(value) == 4 and all(type(v) in (int, float) for v in value):
        west, south, east, north = value
        return vertices(corners((south, west, north, east)), minimum=10)
    if not isinstance(value, dict) or value.get("type") != "Polygon":
        raise ValueError("area: send a GeoJSON Polygon (or Feature) or a [west, south, east, north] bbox.")
    rings = value.get("coordinates")
    if not isinstance(rings, list) or not rings or not isinstance(rings[0], list):
        raise ValueError("area: Polygon needs at least one ring of [lon, lat] positions.")
    # Holes are ignored: a capture area with a hole is still captured to its outer edge.
    points = []
    for position in rings[0]:
        if not isinstance(position, list) or len(position) < 2:
            raise ValueError("area: each position must be [lon, lat].")
        points.append((position[1], position[0]))
    return vertices(points, minimum=10)


def to_geojson(polygon):
    ring = [[lon, lat] for lat, lon in polygon]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def area_km2(polygon):
    return measure(polygon)[0] / 1e6


def parse_layers(value, available):
    if value is None:
        value = [layer for layer in LAYERS if layer in available]
    if not isinstance(value, list) or not value:
        raise ValueError("layers: choose one or more of " + ", ".join(LAYERS))
    unknown = [v for v in value if v not in LAYERS]
    if unknown:
        raise ValueError(f"layers: unknown {', '.join(map(str, unknown))}")
    missing = [v for v in value if v not in available]
    if missing:
        raise ValueError(f"layers: not available on this server: {', '.join(missing)}")
    return [layer for layer in LAYERS if layer in value]


def dted_cells(polygon):
    south, west, north, east = extent(polygon)
    rows = range(math.floor(south), max(math.ceil(north), math.floor(south) + 1))
    cols = range(math.floor(west), max(math.ceil(east), math.floor(west) + 1))
    return [(lat, lon) for lat in rows for lon in cols]


def estimate(polygon, layers, options, settings):
    """Bytes and rough seconds per layer, for the confirm-before-submit step every client shows."""
    from .layers.elevation import post_spacing  # local: keeps area importable without numpy

    result = {"area_km2": round(area_km2(polygon), 3), "layers": {}}
    if "imagery" in layers:
        zoom = options["imagery_zoom"]
        count = grid(polygon, zoom)["count"]
        size = count * JPEG_TILE_BYTES * OVERVIEW_FACTOR
        if "geotiff" in options["imagery_formats"]:
            size += count * COG_TILE_BYTES * OVERVIEW_FACTOR
        result["layers"]["imagery"] = dict(tiles=count, zoom=zoom, bytes=int(size), seconds=math.ceil(count * 0.3 / 8))
    if "elevation" in layers:
        south, west, north, east = extent(polygon)
        lat_step, lon_step = post_spacing(options["dted_level"], (south + north) / 2)
        posts = ((north - south) * 3600 / lat_step + 1) * ((east - west) * 3600 / lon_step + 1)
        cells = len(dted_cells(polygon))
        tiles = grid(corners(extent(polygon)), options["elevation_zoom"])["count"]
        size = posts * (DTED_POST_BYTES + GEOTIFF_POST_BYTES) + cells * DTED_EMPTY_CELL_BYTES
        result["layers"]["elevation"] = dict(dted_cells=cells, dted_level=options["dted_level"], tiles=tiles,
                                             bytes=int(size), seconds=math.ceil(tiles * 0.7 / 8) + 2 * cells)
    if "osm" in layers:
        result["layers"]["osm"] = dict(bytes=int(result["area_km2"] * OSM_BYTES_PER_KM2),
                                       # First capture in a region downloads its Geofabrik extract.
                                       seconds=60)
    if "photos" in layers:
        limit = settings["photos"]["limit"]
        result["layers"]["photos"] = dict(max_photos=limit, bytes=limit * PHOTO_BYTES, seconds=math.ceil(limit * 0.5 / 8),
                                          note="Upper bound; street-level coverage is sparse outside towns.")
    result["bytes"] = sum(layer["bytes"] for layer in result["layers"].values())
    result["seconds"] = sum(layer["seconds"] for layer in result["layers"].values())
    result["max_area_km2"] = settings["max_area_km2"]
    result["allowed"] = result["area_km2"] <= settings["max_area_km2"]
    return result
