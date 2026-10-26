"""Elevation: Terrarium tiles → a Web Mercator height mosaic → DTED cells for ATAK plus a
Float32 GeoTIFF for GIS.

DTED posts sit on a fixed arc-second lattice per 1° cell, so heights are resampled
(bilinear) from the mosaic at exactly those posts. Posts outside the capture's bounding box are
written as void, so a 2 km² capture yields a valid but mostly-empty cell.
"""

import math
import shutil
import zipfile
from io import BytesIO

import numpy as np
from PIL import Image

from .. import sources
from ..core.common import write_bytes
from ..core.geo import corners, extent, grid, tiles
from ..formats import dted, geotiff
from ..formats.datapackage import Entry
from ..net import Failures, fetch_each
from . import LayerResult

WORKERS = 8


def post_spacing(level, latitude):
    """(lat, lon) post spacing in arc-seconds at a latitude."""
    lat_int, lon_int = dted.intervals(level, math.floor(latitude))
    return lat_int / 10, lon_int / 10


def decode_terrarium(data):
    with Image.open(BytesIO(data)) as image:
        if image.size != (256, 256):
            raise ValueError("Expected a 256 × 256 Terrarium tile.")
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


class Mosaic:
    """Heights for every pixel of a tile grid, NaN where a tile was unavailable."""

    def __init__(self, root, plan):
        self.zoom, self.x0, self.y0 = plan["zoom"], plan["x0"], plan["y0"]
        self.heights = np.full((plan["rows"] * 256, plan["columns"] * 256), np.nan, dtype=np.float32)
        for tile in tiles(plan):
            path = root / f"{self.zoom}/{tile['x']}/{tile['y']}.png"
            if path.is_file():
                row, column = tile["row"] * 256, tile["column"] * 256
                self.heights[row:row + 256, column:column + 256] = decode_terrarium(path.read_bytes())

    def sample(self, lats, lons):
        """Bilinear heights at arrays of positions; NaN if any neighbour is missing or off-grid."""
        size = 256 * 2**self.zoom
        lats = np.clip(lats, -85.0511287798066, 85.0511287798066)
        px = (np.asarray(lons) + 180) / 360 * size - self.x0 * 256 - 0.5
        py = (1 - np.arcsinh(np.tan(np.radians(lats))) / math.pi) / 2 * size - self.y0 * 256 - 0.5
        height, width = self.heights.shape
        x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
        fx, fy = px - x0, py - y0
        x0, y0 = np.clip(x0, 0, width - 1), np.clip(y0, 0, height - 1)
        x1, y1 = np.clip(x0 + 1, 0, width - 1), np.clip(y0 + 1, 0, height - 1)
        h = self.heights
        top = h[y0, x0] * (1 - fx) + h[y0, x1] * fx
        bottom = h[y1, x0] * (1 - fx) + h[y1, x1] * fx
        return top * (1 - fy) + bottom * fy


def download(ctx, plan, root):
    pending = [t for t in tiles(plan) if not (root / f"{plan['zoom']}/{t['x']}/{t['y']}.png").is_file()]
    done = plan["count"] - len(pending)
    ctx.progress("Downloading elevation", done, plan["count"])
    addresses = [sources.TERRAIN_URL.format(z=plan["zoom"], x=t["x"], y=t["y"]) for t in pending]
    failures = Failures("Elevation", plan["count"])
    missing = 0
    for tile, data in zip(pending, fetch_each(ctx.client, addresses, WORKERS)):
        if isinstance(data, Exception):
            failures.add(data)
        elif data is None:
            missing += 1
        else:
            decode_terrarium(data)  # reject a corrupt tile now, not halfway through DTED writing
            write_bytes(root / f"{plan['zoom']}/{tile['x']}/{tile['y']}.png", data)
        done += 1
        ctx.progress("Downloading elevation", done, plan["count"])
    if missing == plan["count"]:
        raise OSError("No elevation tiles were available for this area.")
    # Void posts in a DTED cell are worse than a clear failure: any failed tile fails the layer.
    failures.tolerance = 0
    failures.check(downloaded_any=True)
    return missing


def write_cells(ctx, mosaic, bbox, level, dted_root):
    south, west, north, east = bbox
    cells = dted.cells_for(south, west, north, east)
    written = []
    for i, (cell_lat, cell_lon) in enumerate(cells):
        ctx.progress("Writing DTED", i, len(cells))
        lats, lons = dted.post_coordinates(cell_lat, cell_lon, level)
        heights = np.full((len(lons), len(lats)), np.nan)
        lat_index = np.nonzero((lats >= south) & (lats <= north))[0]
        lon_index = np.nonzero((lons >= west) & (lons <= east))[0]
        if len(lat_index) and len(lon_index):
            grid_lons, grid_lats = np.meshgrid(lons[lon_index], lats[lat_index], indexing="ij")
            heights[np.ix_(lon_index, lat_index)] = mosaic.sample(grid_lats, grid_lons)
        relative = dted.cell_path(cell_lat, cell_lon, level)
        (dted_root / relative).parent.mkdir(parents=True, exist_ok=True)
        dted.write(dted_root / relative, cell_lat, cell_lon, level, heights)
        written.append(relative)
    ctx.progress("Writing DTED", len(cells), len(cells))
    return written


def write_geotiff(mosaic, bbox, level, path):
    south, west, north, east = bbox
    lat_step, lon_step = (v / 3600 for v in post_spacing(level, (south + north) / 2))
    # Snap to the same arc-second lattice as the DTED posts so both outputs agree post-for-post.
    lats = np.arange(math.floor(north / lat_step), math.ceil(south / lat_step) - 1, -1) * lat_step
    lons = np.arange(math.ceil(west / lon_step), math.floor(east / lon_step) + 1) * lon_step
    grid_lons, grid_lats = np.meshgrid(lons, lats)
    heights = mosaic.sample(grid_lats, grid_lons)
    geotiff.write(path, heights, float(lons[0]), float(lats[0]), lon_step, lat_step)
    finite = heights[np.isfinite(heights)]
    return (float(finite.min()), float(finite.max())) if finite.size else (None, None)


def run(ctx):
    bbox = extent(ctx.polygon)
    plan = grid(corners(bbox), ctx.options["elevation_zoom"])
    root = ctx.work("elevation") / "tiles"
    missing = download(ctx, plan, root)
    mosaic = Mosaic(root, plan)
    level = ctx.options["dted_level"]

    dted_root = ctx.work("elevation") / "DTED"
    shutil.rmtree(dted_root, ignore_errors=True)
    cells = write_cells(ctx, mosaic, bbox, level, dted_root)

    out = ctx.output()
    dted_zip = out / f"{ctx.name}-dted.zip"
    # The nested zip mirrors ATAK's own DTED folder (DTED/w089/n39.dt2).
    with zipfile.ZipFile(dted_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in cells:
            archive.write(dted_root / relative, f"DTED/{relative}")
    tif = out / f"{ctx.name}-elevation.tif"
    ctx.progress("Writing elevation GeoTIFF")
    low, high = write_geotiff(mosaic, bbox, level, tif)

    result = LayerResult(attribution=sources.TERRAIN_ATTRIBUTION)
    # ignore="true": these cells are void outside the capture, and many devices already hold
    # complete DTED for the whole state. A generic import could replace a full cell with a
    # mostly-empty one, so only the ATAK plugin installs them — merging, filling voids only.
    # Clients without the plugin can still import the nested zip by hand.
    result.entries.append(Entry(f"elevation/{ctx.name}-dted.zip", dted_zip, ignore=True))
    # TAK clients would treat a Float32 GeoTIFF as imagery; keep it in the package, unimported.
    result.entries.append(Entry(f"elevation/{ctx.name}-elevation.tif", tif, ignore=True))
    if missing:
        result.warnings.append(f"Elevation: {missing} of {plan['count']} tiles were unavailable (void posts).")
    result.stats = dict(dted_level=level, dted_cells=cells, zoom=plan["zoom"],
                        min_m=None if low is None else round(low, 1), max_m=None if high is None else round(high, 1))
    return result
