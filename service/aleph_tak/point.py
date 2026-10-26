"""Point mode: tap a spot, get its elevation, nearest address, and nearby street-level photos.

Each part degrades on its own — a geocoder outage still returns the elevation.
"""

import json
import math
from urllib.parse import urlencode

from . import sources
from .core import places
from .core.geo import distance
from .layers.elevation import decode_terrarium

ELEVATION_ZOOM = 14
PHOTO_RADIUS_M = 150


def elevation_at(client, lat, lon):
    size = 256 * 2**ELEVATION_ZOOM
    px = (lon + 180) / 360 * size
    py = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size
    x, y = int(px // 256), int(py // 256)
    heights = decode_terrarium(client.get(sources.TERRAIN_URL.format(z=ELEVATION_ZOOM, x=x, y=y)))
    column, row = min(255, int(px - x * 256)), min(255, int(py - y * 256))
    return round(float(heights[row, column]), 1)


def nearby_photos(client, token, lat, lon, limit=5):
    d_lat = PHOTO_RADIUS_M / 111_320
    d_lon = d_lat / max(0.01, math.cos(math.radians(lat)))
    params = dict(access_token=token, fields="id,geometry,captured_at,compass_angle,thumb_256_url,thumb_1024_url",
                  bbox=f"{lon - d_lon},{lat - d_lat},{lon + d_lon},{lat + d_lat}", limit=50)
    data = json.loads(client.get(f"{sources.MAPILLARY_GRAPH}/images?{urlencode(params)}"))
    result = []
    for photo in data.get("data", []):
        plon, plat = photo["geometry"]["coordinates"]
        result.append(dict(id=photo["id"], lat=plat, lon=plon, distance_m=round(distance((lat, lon), (plat, plon)), 1),
                           captured_at=photo.get("captured_at"), compass_angle=photo.get("compass_angle"),
                           thumb_url=photo.get("thumb_256_url"), image_url=photo.get("thumb_1024_url")))
    return sorted(result, key=lambda p: p["distance_m"])[:limit]


def lookup(client, settings, lat, lon):
    result = dict(lat=lat, lon=lon, errors={})
    try:
        result["elevation_m"] = elevation_at(client, lat, lon)
        result["elevation_source"] = "AWS Terrain Tiles"
    except Exception as error:
        result["elevation_m"] = None
        result["errors"]["elevation"] = str(error)
    try:
        found = places.geocode(client, at=(lat, lon), limit=1, endpoint=settings["geocoder_url"])
        result["address"] = found[0] if found else None
    except Exception as error:
        result["address"] = None
        result["errors"]["address"] = str(error)
    token = settings["photos"]["mapillary_token"]
    if token:
        try:
            result["photos"] = nearby_photos(client, token, lat, lon)
        except Exception as error:
            result["photos"] = []
            result["errors"]["photos"] = str(error)
    else:
        result["photos"] = None  # layer not configured on this server
    result["attribution"] = [sources.TERRAIN_ATTRIBUTION, sources.OSM_ATTRIBUTION] + (
        [sources.MAPILLARY_ATTRIBUTION] if token else [])
    return result
