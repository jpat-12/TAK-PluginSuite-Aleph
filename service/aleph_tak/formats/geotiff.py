"""Single-band Float32 GeoTIFF in EPSG:4326, deflate-compressed strips. No GDAL needed.

Used for the elevation layer's GIS-friendly copy (the DTED cells are what ATAK consumes).
Pixel-is-area georeferencing: the tiepoint is the outer corner of the north-west pixel, so a
post at (lat, lon) sits at that pixel's centre.
"""

import struct
import zlib

import numpy as np

from ..core.common import atomic_path

NODATA = -32767.0
ROWS_PER_STRIP = 16

# TIFF field types used here.
SHORT, LONG, DOUBLE, ASCII = 3, 4, 12, 2
_FORMATS = {SHORT: "H", LONG: "I", DOUBLE: "d", ASCII: "s"}


def write(path, heights, west, north, x_step, y_step):
    """heights: (rows, cols) north→south, west→east; NaN becomes NODATA. Steps in degrees."""
    heights = np.asarray(heights, dtype=np.float32)
    rows, cols = heights.shape
    heights = np.where(np.isfinite(heights), heights, NODATA).astype("<f4")
    strips = [zlib.compress(heights[r:r + ROWS_PER_STRIP].tobytes(), 6) for r in range(0, rows, ROWS_PER_STRIP)]

    geokeys = [1, 1, 0, 3,
               1024, 0, 1, 2,      # GTModelType: geographic
               1025, 0, 1, 1,      # GTRasterType: pixel is area
               2048, 0, 1, 4326]   # GeographicType: WGS 84
    tags = {
        256: (LONG, [cols]), 257: (LONG, [rows]), 258: (SHORT, [32]), 259: (SHORT, [8]),
        262: (SHORT, [1]), 273: (LONG, [0] * len(strips)), 277: (SHORT, [1]),
        278: (LONG, [ROWS_PER_STRIP]), 279: (LONG, [len(s) for s in strips]), 284: (SHORT, [1]),
        339: (SHORT, [3]),
        33550: (DOUBLE, [x_step, y_step, 0.0]),
        33922: (DOUBLE, [0.0, 0.0, 0.0, west - x_step / 2, north + y_step / 2, 0.0]),
        34735: (SHORT, geokeys),
        42113: (ASCII, [f"{NODATA:g}".encode() + b"\0"]),
    }

    def encode(kind, values):
        if kind == ASCII:
            return values[0]
        return struct.pack("<" + _FORMATS[kind] * len(values), *values)

    # Layout: header, IFD, out-of-line tag values, then strips. Strip offsets only change
    # values, never sizes, so one layout pass with placeholders gives the final positions.
    def layout():
        cursor = 8 + 2 + len(tags) * 12 + 4
        places = {}
        for code, (kind, values) in sorted(tags.items()):
            raw = encode(kind, values)
            if len(raw) > 4:
                cursor += -cursor % 2
                places[code] = cursor
                cursor += len(raw)
        return places, cursor + (-cursor % 8)

    places, data_start = layout()
    offsets, position = [], data_start
    for strip in strips:
        offsets.append(position)
        position += len(strip)
    tags[273] = (LONG, offsets)

    with atomic_path(path) as temporary, temporary.open("wb") as out:
        out.write(struct.pack("<2sHI", b"II", 42, 8))
        out.write(struct.pack("<H", len(tags)))
        for code, (kind, values) in sorted(tags.items()):
            raw = encode(kind, values)
            count = len(raw) if kind == ASCII else len(values)
            out.write(struct.pack("<HHI", code, kind, count))
            out.write(struct.pack("<I", places[code]) if code in places else raw.ljust(4, b"\0"))
        out.write(struct.pack("<I", 0))
        for code in sorted(places):
            out.write(b"\0" * (places[code] - out.tell()))
            out.write(encode(*tags[code]))
        out.write(b"\0" * (data_start - out.tell()))
        for strip in strips:
            out.write(strip)


def read(path):
    """Tiny reader for tests: (array north→south, dict of georeferencing tags)."""
    with open(path, "rb") as stream:
        data = stream.read()
    if data[:4] != b"II*\0":
        raise ValueError("Expected a little-endian TIFF.")
    ifd = struct.unpack_from("<I", data, 4)[0]
    count = struct.unpack_from("<H", data, ifd)[0]
    tags = {}
    for i in range(count):
        code, kind, n, value = struct.unpack_from("<HHI4s", data, ifd + 2 + i * 12)
        size = {SHORT: 2, LONG: 4, DOUBLE: 8, ASCII: 1}[kind] * n
        raw = value[:size] if size <= 4 else data[struct.unpack("<I", value)[0]:][:size]
        tags[code] = raw if kind == ASCII else struct.unpack("<" + _FORMATS[kind] * n, raw)
    cols, rows = tags[256][0], tags[257][0]
    pixels = b"".join(zlib.decompress(data[o:o + n]) for o, n in zip(tags[273], tags[279]))
    return np.frombuffer(pixels, dtype="<f4").reshape(rows, cols), tags
