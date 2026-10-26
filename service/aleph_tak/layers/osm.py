"""OSM features from Geofabrik regional extracts (Aleph's own PBF reader), sorted into the layers a
search team actually uses — roads, trails, water, buildings, power lines, landing zones — and
clipped to the capture area. Output: KMZ for TAK import, GeoJSON for the CloudTAK web map.

The first capture in a region downloads its Geofabrik extract (Illinois ≈ 300 MB) into the
shared cache; later captures there reuse it until Geofabrik publishes a newer one.
"""

from ..core.common import write_json
from ..core.geo import collection, extent, feature, pieces, ring_contains
from ..core.osm import POI_KEYS, Source
from ..core.pbf import PBF
from ..formats import kml
from ..formats.datapackage import Entry
from .. import sources
from . import LayerResult

MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary",
         "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
MINOR = {"residential", "unclassified", "service", "living_street", "road", "busway"}
TRAILS = {"track", "path", "footway", "bridleway", "cycleway", "steps", "pedestrian"}
WATERWAYS = {"river", "stream", "canal", "drain", "ditch"}
PLACE_KEYS = POI_KEYS + ("place", "emergency", "aeroway", "man_made")
# Kept so a tap on a feature in TAK shows what it is without the full OSM tag soup.
DETAIL_KEYS = ("highway", "surface", "tracktype", "access", "waterway", "natural", "building", "power",
               "voltage", "railway", "aeroway", "amenity", "shop", "tourism", "emergency", "place", "ref")


def classify_way(tags, closed):
    if tags.get("aeroway") in ("runway", "helipad", "aerodrome", "heliport"):
        return "aero"
    if "building" in tags and closed:
        return "buildings"
    highway = tags.get("highway")
    if highway in MAJOR:
        return "roads_major"
    if highway in MINOR:
        return "roads_minor"
    if highway in TRAILS:
        return "trails"
    if tags.get("waterway") in WATERWAYS:
        return "waterways"
    if closed and (tags.get("natural") == "water" or "water" in tags or tags.get("landuse") in ("reservoir", "basin")):
        return "water"
    if tags.get("railway") == "rail":
        return "railways"
    if tags.get("power") in ("line", "minor_line"):
        return "power"
    return None


def classify_node(tags):
    if tags.get("aeroway") in ("helipad", "heliport", "aerodrome"):
        return "aero"
    if tags.get("name") and any(key in tags for key in PLACE_KEYS):
        return "places"
    return None


def describe(tags):
    return ", ".join(f"{key}={tags[key]}" for key in DETAIL_KEYS if key in tags)


def to_features(items, polygon):
    """Ways and nodes → GeoJSON features clipped to the polygon; lines are cut at its edge."""
    ring = [*polygon, polygon[0]]
    result = []
    for item in items:
        tags = item.get("tags") or {}
        if item["type"] == "node":
            layer = classify_node(tags)
            center = item.get("center")
            if layer and center and ring_contains(ring, center):
                result.append(feature("Point", [center[1], center[0]],
                                      dict(layer=layer, name=tags.get("name", ""), kind=describe(tags),
                                           osm_id=f"node/{item['id']}")))
            continue
        if item["type"] != "way" or len(item.get("points", ())) < 2:
            continue
        points = item["points"]
        closed = item["nodes"][0] == item["nodes"][-1] and len(points) >= 4
        layer = classify_way(tags, closed)
        if not layer:
            continue
        props = dict(layer=layer, name=tags.get("name", ""), kind=describe(tags), osm_id=f"way/{item['id']}")
        if closed and layer in ("buildings", "water", "aero"):
            # Areas are kept whole when any corner is inside; cutting a building in half helps no one.
            if any(ring_contains(ring, p) for p in points):
                result.append(feature("Polygon", [[[lon, lat] for lat, lon in points]], props))
            continue
        parts = []
        for a, b in zip(points, points[1:]):
            for start, end in pieces(a, b, polygon):
                if parts and parts[-1][-1] == start:
                    parts[-1].append(end)
                else:
                    parts.append([start, end])
        if parts:
            lines = [[[lon, lat] for lat, lon in part] for part in parts]
            if len(lines) == 1:
                result.append(feature("LineString", lines[0], props))
            else:
                result.append(feature("MultiLineString", lines, props))
    return result


def extract(pbf_path, polygon, cancel):
    pbf = PBF(pbf_path, cancel)
    nodes, _, _ = pbf.select(extent(polygon))
    wanted = {identity for identity, way in pbf.selected_ways.items()
              if classify_way(way["tags"], len(way["nodes"]) >= 4 and way["nodes"][0] == way["nodes"][-1])}
    # Relations (multipolygon lakes, large landuse) are skipped in v1 — see README status table.
    return pbf.read((nodes, wanted, set()), centers=True)


def run(ctx):
    region_source = Source(ctx.client)
    ctx.progress("Finding OSM region")
    pbf_path, metadata = region_source.region(extent(ctx.polygon), ctx.progress)
    ctx.progress("Extracting OSM features")
    items = extract(pbf_path, ctx.polygon, ctx.client.check_cancel)
    features = to_features(items, ctx.polygon)

    work, out = ctx.work("osm"), ctx.output()
    write_json(work / "osm.geojson", collection(features))
    kmz = out / f"{ctx.name}-osm.kmz"
    stamp = metadata.get("osm_data_at") or "unknown date"
    kml.write_kmz(kmz, features, f"{ctx.name} — OpenStreetMap",
                  f"{sources.OSM_ATTRIBUTION} Region: {metadata.get('region')}, data as of {stamp}.")

    counts = {}
    for item in features:
        counts[item["properties"]["layer"]] = counts.get(item["properties"]["layer"], 0) + 1
    result = LayerResult(attribution=sources.OSM_ATTRIBUTION)
    result.entries.append(Entry(f"osm/{ctx.name}.kmz", kmz))
    result.stats = dict(features=len(features), by_layer=counts, region=metadata.get("region"), osm_data_at=stamp)
    result.web = dict(geojson="osm")
    return result
