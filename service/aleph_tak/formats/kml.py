"""GeoJSON features → KMZ, one folder per layer, styled for legibility over imagery.

KML is the vector format every TAK client imports without a plugin (ATAK, WinTAK, iTAK).
Colours are KML's aabbggrr, not rrggbb.
"""

import zipfile
from xml.sax.saxutils import escape

from ..core.common import atomic_path

# layer key → (folder title, line colour, line width, polygon fill or None)
STYLES = {
    "roads_major": ("Major roads", "ff00d7ff", 4, None),
    "roads_minor": ("Local roads", "ffffffff", 2, None),
    "trails": ("Trails & tracks", "ff2a6aa5", 2, None),
    "railways": ("Railways", "ff555555", 3, None),
    "power": ("Power lines", "ff0000ff", 2, None),
    "waterways": ("Waterways", "ffff9933", 2, None),
    "water": ("Water", "ffff9933", 1, "66ff9933"),
    "buildings": ("Buildings", "ff0080ff", 1, "4d0080ff"),
    "aero": ("Airfields & helipads", "ffff00ff", 2, "33ff00ff"),
    "places": ("Places", "ffffffff", 1, None),
}


def _coords(positions):
    return " ".join(f"{lon:.7f},{lat:.7f}" for lon, lat, *_ in positions)


def _geometry(geometry):
    kind, coordinates = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return f"<Point><coordinates>{_coords([coordinates])}</coordinates></Point>"
    if kind == "LineString":
        return f"<LineString><tessellate>1</tessellate><coordinates>{_coords(coordinates)}</coordinates></LineString>"
    if kind == "MultiLineString":
        return "<MultiGeometry>" + "".join(_geometry({"type": "LineString", "coordinates": part})
                                           for part in coordinates) + "</MultiGeometry>"
    if kind == "Polygon":
        rings = [f"<outerBoundaryIs><LinearRing><coordinates>{_coords(coordinates[0])}</coordinates></LinearRing></outerBoundaryIs>"]
        rings += [f"<innerBoundaryIs><LinearRing><coordinates>{_coords(ring)}</coordinates></LinearRing></innerBoundaryIs>"
                  for ring in coordinates[1:]]
        return "<Polygon>" + "".join(rings) + "</Polygon>"
    raise ValueError(f"Unsupported geometry for KML: {kind}")


def _style(key):
    _, line, width, fill = STYLES[key]
    poly = f"<PolyStyle><color>{fill}</color></PolyStyle>" if fill else "<PolyStyle><fill>0</fill></PolyStyle>"
    return f'<Style id="{key}"><LineStyle><color>{line}</color><width>{width}</width></LineStyle>{poly}</Style>'


def document(features, title, description):
    by_layer = {}
    for feature in features:
        by_layer.setdefault(feature["properties"]["layer"], []).append(feature)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
             f"<name>{escape(title)}</name><description>{escape(description)}</description>"]
    parts += [_style(key) for key in STYLES if key in by_layer]
    for key in STYLES:
        if key not in by_layer:
            continue
        parts.append(f"<Folder><name>{escape(STYLES[key][0])}</name>")
        for feature in by_layer[key]:
            props = feature["properties"]
            name = props.get("name") or ""
            details = props.get("kind") or ""
            parts.append(f"<Placemark><name>{escape(name)}</name>"
                         f"<description>{escape(details)}</description>"
                         f"<styleUrl>#{key}</styleUrl>{_geometry(feature['geometry'])}</Placemark>")
        parts.append("</Folder>")
    parts.append("</Document></kml>\n")
    return "".join(parts)


def write_kmz(path, features, title, description):
    with atomic_path(path) as temporary:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as kmz:
            kmz.writestr("doc.kml", document(features, title, description))
