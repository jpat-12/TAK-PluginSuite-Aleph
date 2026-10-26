"""DTED level 1/2 writer (MIL-PRF-89020B), pure Python + numpy.

ATAK's elevation store is a tree of whole 1°×1° cells: atak/DTED/w089/n39.dt2. A capture only
covers a few km², so each cell we write holds real posts inside the captured area and the
standard void value (-32767) everywhere else — a legal, mostly-void cell that zips to almost
nothing.

Layout: UHL (80 B) + DSI (648 B) + ACC (2700 B), then one record per longitude line, west to
east. Each record is 0xAA, a 3-byte block count, 2-byte longitude and latitude counts, the
posts south to north as *signed-magnitude* big-endian int16 (not two's complement), and a
4-byte sum of every preceding byte in the record.
"""

import math

import numpy as np

VOID = -32767
HEADER_BYTES = 80 + 648 + 2700


def lon_multiplier(cell_lat):
    """Longitude spacing grows toward the poles (spec zones I–V), keyed by the cell's equator-side edge."""
    a = min(abs(cell_lat), abs(cell_lat + 1))
    return 1 if a < 50 else 2 if a < 70 else 3 if a < 75 else 4 if a < 80 else 6


def intervals(level, cell_lat):
    """(lat, lon) post spacing in tenths of arc-seconds."""
    if level not in (1, 2):
        raise ValueError("DTED level must be 1 or 2.")
    lat = 30 if level == 1 else 10
    return lat, lat * lon_multiplier(cell_lat)


def shape(level, cell_lat):
    lat, lon = intervals(level, cell_lat)
    return 36000 // lat + 1, 36000 // lon + 1  # (posts per profile, profiles)


def cell_path(cell_lat, cell_lon, level):
    """Path relative to the DTED root: w089/n39.dt2 (lower-case, as ATAK and GDAL expect)."""
    return (f"{'e' if cell_lon >= 0 else 'w'}{abs(cell_lon):03d}/"
            f"{'n' if cell_lat >= 0 else 's'}{abs(cell_lat):02d}.dt{level}")


def _dms(value, degree_digits, positive, negative, seconds_decimal=False):
    hemisphere = positive if value >= 0 else negative
    value = abs(value)
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = round(((value - degrees) * 60 - minutes) * 60, 1)
    if seconds_decimal:
        return f"{degrees:0{degree_digits}d}{minutes:02d}{seconds:04.1f}{hemisphere}"
    return f"{degrees:0{degree_digits}d}{minutes:02d}{int(seconds):02d}{hemisphere}"


def _field(text, width):
    text = str(text)
    if len(text) > width:
        raise ValueError(f"DTED field too long: {text!r} > {width}")
    return text.ljust(width)


def headers(cell_lat, cell_lon, level, *, reference="ALEPH-TAK", compiled="0000"):
    lat_int, lon_int = intervals(level, cell_lat)
    rows, cols = shape(level, cell_lat)
    uhl = ("UHL1" + _dms(cell_lon, 3, "E", "W") + _dms(cell_lat, 3, "N", "S")
           + f"{lon_int:04d}{lat_int:04d}" + "NA  " + "U  " + _field(reference, 12)
           + f"{cols:04d}{rows:04d}" + "0" + " " * 24)

    def corner(lat, lon):
        return _dms(lat, 2, "N", "S") + _dms(lon, 3, "E", "W")

    dsi = ("DSI" + "U" + "  " + " " * 27 + " " * 26 + _field(f"DTED{level}", 5) + _field(reference, 15)
           + " " * 8 + "01" + "A" + "0000" + "0000" + "0000" + _field("ALEPHTAK", 8) + " " * 16
           + "PRF89020B" + "00" + "0005" + "E96" + "WGS84" + _field("ALEPH-TAK", 10) + compiled + " " * 22
           + _dms(cell_lat, 2, "N", "S", True) + _dms(cell_lon, 3, "E", "W", True)
           + corner(cell_lat, cell_lon) + corner(cell_lat + 1, cell_lon)
           + corner(cell_lat + 1, cell_lon + 1) + corner(cell_lat, cell_lon + 1)
           + "0000000.0" + f"{lat_int:04d}{lon_int:04d}" + f"{rows:04d}{cols:04d}" + "00")
    dsi = dsi.ljust(648)
    acc = ("ACC" + "NA  " * 4 + " " * 4 + " " + " " * 31 + "00").ljust(2700)
    for name, record, size in (("UHL", uhl, 80), ("DSI", dsi, 648), ("ACC", acc, 2700)):
        if len(record) != size:
            raise AssertionError(f"{name} is {len(record)} bytes, expected {size}")
    return (uhl + dsi + acc).encode("ascii")


def encode_posts(heights):
    """int heights → signed-magnitude big-endian bytes; VOID encodes as 0xFFFF."""
    values = np.clip(np.asarray(heights, dtype=np.int32), -32767, 32767)
    magnitude = np.abs(values).astype(np.uint16)
    magnitude[values < 0] |= 0x8000
    return magnitude.astype(">u2").tobytes()


def write(path, cell_lat, cell_lon, level, heights):
    """heights: (profiles, posts) array — [i, j] is longitude line i (west→east), post j (south→north).

    Pass VOID (or NaN) where there's no data.
    """
    rows, cols = shape(level, cell_lat)
    heights = np.asarray(heights, dtype=np.float64)
    if heights.shape != (cols, rows):
        raise ValueError(f"Cell {cell_lat},{cell_lon} level {level} needs {(cols, rows)} posts, got {heights.shape}")
    heights = np.where(np.isfinite(heights), np.rint(heights), VOID)
    with open(path, "wb") as stream:
        stream.write(headers(cell_lat, cell_lon, level))
        for i in range(cols):
            record = bytearray(b"\xaa" + i.to_bytes(3, "big") + i.to_bytes(2, "big") + b"\0\0")
            record += encode_posts(heights[i])
            record += (sum(record) & 0xFFFFFFFF).to_bytes(4, "big")
            stream.write(record)


def read(path):
    """Minimal reader for tests and the package self-check: (header dict, (profiles, posts) array)."""
    with open(path, "rb") as stream:
        data = stream.read()
    uhl = data[:80].decode("ascii")
    if not uhl.startswith("UHL1"):
        raise ValueError("Not a DTED file (no UHL).")
    cols, rows = int(uhl[47:51]), int(uhl[51:55])
    record = 12 + rows * 2
    if len(data) != HEADER_BYTES + cols * record:
        raise ValueError("DTED size does not match its header.")
    heights = np.empty((cols, rows), dtype=np.int32)
    for i in range(cols):
        start = HEADER_BYTES + i * record
        raw = data[start:start + record]
        if raw[0] != 0xAA:
            raise ValueError(f"Bad record sentinel at profile {i}.")
        if int.from_bytes(raw[-4:], "big") != (sum(raw[:-4]) & 0xFFFFFFFF):
            raise ValueError(f"Bad checksum at profile {i}.")
        words = np.frombuffer(raw[8:-4], dtype=">u2").astype(np.int32)
        heights[i] = np.where(words & 0x8000, -(words & 0x7FFF), words)
    return dict(lon_origin=uhl[4:12], lat_origin=uhl[12:20], lon_interval=int(uhl[20:24]),
                lat_interval=int(uhl[24:28]), profiles=cols, posts=rows), heights


def post_coordinates(cell_lat, cell_lon, level):
    """Latitudes (south→north) and longitudes (west→east) of every post in a cell."""
    lat_int, lon_int = intervals(level, cell_lat)
    rows, cols = shape(level, cell_lat)
    lats = cell_lat + np.arange(rows) * (lat_int / 36000)
    lons = cell_lon + np.arange(cols) * (lon_int / 36000)
    return lats, lons


def cells_for(south, west, north, east):
    """Whole cells meeting a bbox; an edge exactly on a degree line doesn't pull in its neighbour."""
    rows = range(math.floor(south), max(math.ceil(north), math.floor(south) + 1))
    cols = range(math.floor(west), max(math.ceil(east), math.floor(west) + 1))
    return [(lat, lon) for lat in rows for lon in cols]
