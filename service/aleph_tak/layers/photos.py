"""Street-level photos from Mapillary (CC BY-SA 4.0) — the replacement for Aleph's Street View.

Needs a Mapillary client token in the service settings; without one the layer is unavailable.
Coverage is sparse in rural areas (plan: treat photos as a bonus layer), so an empty result is
a warning, not a failure. Each photo becomes an ATAK Quick Pic marker with the image attached.
"""

import json
import math
from datetime import datetime, timezone
from urllib.parse import urlencode

from .. import sources
from ..core.common import fetch, write_bytes, write_json
from ..core.geo import collection, extent, feature, ring_contains
from ..formats.cot import photo_marker
from ..formats.datapackage import Entry
from . import LayerResult

# Mapillary rejects bbox searches over ~0.01 square degrees; 0.05° cells stay well under.
QUERY_STEP = 0.05
FIELDS = "id,geometry,captured_at,compass_angle,thumb_1024_url,thumb_256_url,creator"
WORKERS = 4


def search(client, token, south, west, north, east, *, limit=2000):
    params = dict(access_token=token, fields=FIELDS, bbox=f"{west},{south},{east},{north}", limit=limit)
    data = json.loads(client.get(f"{sources.MAPILLARY_GRAPH}/images?{urlencode(params)}"))
    return data.get("data", [])


def query_cells(south, west, north, east):
    rows = max(1, math.ceil((north - south) / QUERY_STEP))
    cols = max(1, math.ceil((east - west) / QUERY_STEP))
    for r in range(rows):
        for c in range(cols):
            yield (south + r * (north - south) / rows, west + c * (east - west) / cols,
                   south + (r + 1) * (north - south) / rows, west + (c + 1) * (east - west) / cols)


def thin(photos, polygon, limit):
    """Newest photo per grid bucket, buckets sized so the area holds ~limit of them."""
    if len(photos) <= limit:
        return sorted(photos, key=lambda p: p.get("captured_at") or 0, reverse=True)
    south, west, north, east = extent(polygon)
    step = max((north - south) * (east - west) / limit, 1e-12) ** 0.5
    buckets = {}
    for photo in sorted(photos, key=lambda p: p.get("captured_at") or 0, reverse=True):
        lon, lat = photo["geometry"]["coordinates"]
        buckets.setdefault((math.floor(lat / step), math.floor(lon / step)), photo)
    return list(buckets.values())[:limit]


def callsign(photo):
    captured = photo.get("captured_at")
    if captured:
        return "Photo " + datetime.fromtimestamp(captured / 1000, timezone.utc).strftime("%Y-%m-%d")
    return "Photo"


def run(ctx):
    token = ctx.settings["photos"]["mapillary_token"]
    if not token:
        raise ValueError("Photos need a Mapillary token in the service settings.")
    limit = ctx.settings["photos"]["limit"]
    south, west, north, east = extent(ctx.polygon)
    ring = [*ctx.polygon, ctx.polygon[0]]

    ctx.progress("Searching street-level photos")
    found = {}
    for cell in query_cells(south, west, north, east):
        for photo in search(ctx.client, token, *cell):
            lon, lat = photo["geometry"]["coordinates"]
            if ring_contains(ring, (lat, lon)):
                found[photo["id"]] = photo
    chosen = thin(list(found.values()), ctx.polygon, limit)

    work = ctx.work("photos")
    pending = [p for p in chosen if not (work / f"{p['id']}.jpg").is_file() and p.get("thumb_1024_url")]
    ctx.progress("Downloading photos", len(chosen) - len(pending), len(chosen))
    done = len(chosen) - len(pending)
    for photo, data in zip(pending, fetch(ctx.client, [p["thumb_1024_url"] for p in pending], WORKERS, missing_ok=True)):
        if data is not None:
            write_bytes(work / f"{photo['id']}.jpg", data)
        done += 1
        ctx.progress("Downloading photos", done, len(chosen))

    result = LayerResult(attribution=sources.MAPILLARY_ATTRIBUTION)
    features = []
    for photo in chosen:
        image = work / f"{photo['id']}.jpg"
        if not image.is_file():
            continue
        lon, lat = photo["geometry"]["coordinates"]
        uid = f"aleph-photo-{photo['id']}"
        creator = (photo.get("creator") or {}).get("username") or "a Mapillary contributor"
        heading = photo.get("compass_angle")
        remarks = (f"Street-level photo by {creator}, CC BY-SA 4.0, via Mapillary (image {photo['id']})."
                   + (f" Camera heading {heading:.0f}°." if heading is not None else ""))
        result.entries.append(Entry(f"photos/{uid}.cot", data=photo_marker(uid, lat, lon, callsign(photo), remarks),
                                    uid=uid))
        result.entries.append(Entry(f"photos/{uid}/{photo['id']}.jpg", image, uid=uid))
        features.append(feature("Point", [lon, lat], dict(id=photo["id"], uid=uid, captured_at=photo.get("captured_at"),
                                                          compass_angle=heading, creator=creator)))
    write_json(work / "photos.geojson", collection(features))
    if not features:
        result.warnings.append("Photos: no street-level photos were found in this area.")
    result.stats = dict(found=len(found), included=len(features))
    result.web = dict(geojson="photos")
    return result
