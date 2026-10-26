"""Imagery: download 256 px tiles over the polygon from an open source, build an overview
pyramid, and write MBTiles (default) and optionally Aleph's lossless COG.

Tiles live in work/imagery/tiles/{z}/{x}/{y}.{jpg|png} — the same XYZ tree the service serves
to CloudTAK, so the web map and the package are built from identical pixels.
"""

import math
from io import BytesIO
from pathlib import Path

from PIL import Image

from .. import sources
from ..core import satellite
from ..core.common import MissingImagery, open_image, write_bytes
from ..core.geo import MERCATOR_RADIUS, extent, grid, tiles
from ..formats import mbtiles
from ..formats.datapackage import Entry
from ..net import Failures, fetch_each
from . import LayerResult

OVERVIEW_LEVELS = 6     # z17 capture → overviews down to z11, enough to find it when zoomed out
JPEG_QUALITY = 85
WORKERS = 8


def tile_path(root, zoom, x, y):
    """Existing tile file (.jpg full, .png partial/transparent), or None."""
    for extension in ("jpg", "png"):
        path = root / str(zoom) / str(x) / f"{y}.{extension}"
        if path.is_file():
            return path
    return None


def _missing_marker(root, zoom, x, y):
    return root / str(zoom) / str(x) / f"{y}.missing"


def download(ctx, source, zoom, root):
    plan = grid(ctx.polygon, zoom)
    pending = [t for t in tiles(plan)
               if tile_path(root, zoom, t["x"], t["y"]) is None
               and not _missing_marker(root, zoom, t["x"], t["y"]).exists()]
    done = plan["count"] - len(pending)
    ctx.progress("Downloading imagery", done, plan["count"])
    addresses = [sources.imagery_url(source, t["x"], t["y"], zoom) for t in pending]
    failures = Failures("Imagery", plan["count"])
    # ArcGIS ImageServers render each tile on request and answer bursts with 502s.
    workers = 4 if source["kind"] == "arcgis-export" else WORKERS
    for tile, data in zip(pending, fetch_each(ctx.client, addresses, workers)):
        if isinstance(data, Exception):
            failures.add(data)  # not persisted: a retry fetches it again
        elif data is None:
            # Persist the gap so a resume doesn't re-request it and the pyramid keeps it transparent.
            write_bytes(_missing_marker(root, zoom, tile["x"], tile["y"]), b"")
        else:
            with open_image(data, (256, 256)) as image:
                if image.format == "JPEG":
                    payload, extension = data, "jpg"
                else:
                    with BytesIO() as buffer:
                        image.convert("RGBA").save(buffer, "PNG")
                        payload, extension = buffer.getvalue(), "png"
            write_bytes(root / str(zoom) / str(tile["x"]) / f"{tile['y']}.{extension}", payload)
        done += 1
        ctx.progress("Downloading imagery", done, plan["count"])
    missing = sum(_missing_marker(root, zoom, t["x"], t["y"]).exists() for t in tiles(plan))
    if missing == plan["count"]:
        raise MissingImagery(f"{source['name']} has no imagery for this area ({source['coverage']}).")
    failures.check(downloaded_any=missing + failures.count < plan["count"])
    return plan, missing, failures


def _load(path):
    with Image.open(path) as image:
        return image.convert("RGBA")


def build_overviews(ctx, root, zoom, levels):
    """Each parent = its four children shrunk 2×. A parent with any gap is PNG (alpha), else JPEG."""
    present = {(x, y) for x, y in _tiles_at(root, zoom)}
    for level in range(zoom - 1, max(zoom - levels, 0) - 1, -1):
        parents = sorted({(x // 2, y // 2) for x, y in present})
        ctx.progress(f"Building overviews z{level}", 0, len(parents))
        for i, (px, py) in enumerate(parents, 1):
            canvas = Image.new("RGBA", (512, 512))
            complete = True
            for dx in (0, 1):
                for dy in (0, 1):
                    child = tile_path(root, level + 1, px * 2 + dx, py * 2 + dy)
                    if child is None:
                        complete = False
                        continue
                    with _load(child) as image:
                        canvas.paste(image, (dx * 256, dy * 256))
                        if child.suffix == ".png" and image.getextrema()[3][0] < 255:
                            complete = False
            with canvas.resize((256, 256), Image.Resampling.LANCZOS) as small:
                target = root / str(level) / str(px)
                target.mkdir(parents=True, exist_ok=True)
                with BytesIO() as buffer:
                    if complete:
                        small.convert("RGB").save(buffer, "JPEG", quality=JPEG_QUALITY)
                        write_bytes(target / f"{py}.jpg", buffer.getvalue())
                        (target / f"{py}.png").unlink(missing_ok=True)
                    else:
                        small.save(buffer, "PNG", optimize=True)
                        write_bytes(target / f"{py}.png", buffer.getvalue())
                        (target / f"{py}.jpg").unlink(missing_ok=True)
            canvas.close()
            ctx.progress(f"Building overviews z{level}", i, len(parents))
        present = set(parents)


def _tiles_at(root, zoom):
    base = root / str(zoom)
    if not base.is_dir():
        return
    for column in base.iterdir():
        for item in column.iterdir():
            if item.suffix in (".jpg", ".png"):
                yield int(column.name), int(item.stem)


def pyramid(root, min_zoom, max_zoom):
    for zoom in range(min_zoom, max_zoom + 1):
        for x, y in sorted(_tiles_at(root, zoom)):
            yield zoom, x, y, tile_path(root, zoom, x, y).read_bytes()


def build_cog(ctx, root, plan, out_path):
    """Reuse Aleph's lossless COG writer; it wants every planned tile, so gaps get a blank PNG."""
    blank = root / "blank.png"
    if not blank.exists():
        with BytesIO() as buffer, Image.new("RGBA", (256, 256)) as image:
            image.save(buffer, "PNG")
            write_bytes(blank, buffer.getvalue())
    results = []
    for tile in tiles(plan):
        path = tile_path(root, plan["zoom"], tile["x"], tile["y"]) or blank
        results.append(dict(tile, filename=Path(path).relative_to(root).as_posix()))
    satellite.merge(dict(grid=plan, results=results), root, ctx.progress, ctx.polygon, name="capture.tif")
    (root / "capture.tif").replace(out_path)


def run(ctx):
    source = sources.imagery_source(ctx.settings)
    zoom = min(ctx.options["imagery_zoom"], source["max_zoom"])
    root = ctx.work("imagery") / "tiles"
    plan, missing, failures = download(ctx, source, zoom, root)
    min_zoom = max(zoom - OVERVIEW_LEVELS, 0)
    build_overviews(ctx, root, zoom, OVERVIEW_LEVELS)

    south, west, north, east = extent(ctx.polygon)
    out = ctx.output()
    mb_path = out / f"{ctx.name}.mbtiles"
    ctx.progress("Writing MBTiles")
    mbtiles.write(mb_path, pyramid(root, min_zoom, zoom), {
        "name": ctx.name, "type": "overlay", "version": "1.1", "format": "jpg",
        "description": f"Aleph for TAK capture — {source['name']}",
        "bounds": f"{west:.7f},{south:.7f},{east:.7f},{north:.7f}",
        "center": f"{(west + east) / 2:.7f},{(south + north) / 2:.7f},{zoom}",
        "minzoom": min_zoom, "maxzoom": zoom, "attribution": source["attribution"],
    })
    result = LayerResult(attribution=source["attribution"])
    result.entries.append(Entry(f"imagery/{ctx.name}.mbtiles", mb_path))
    if "geotiff" in ctx.options["imagery_formats"]:
        cog_path = out / f"{ctx.name}.tif"
        build_cog(ctx, root, plan, cog_path)
        result.entries.append(Entry(f"imagery/{ctx.name}.tif", cog_path))
    if missing:
        result.warnings.append(f"Imagery: {missing} of {plan['count']} tiles had no coverage and are transparent.")
    if failures.warning():
        result.warnings.append(failures.warning())
    latitude = math.radians((south + north) / 2)
    resolution = 2 * math.pi * MERCATOR_RADIUS * math.cos(latitude) / (256 * 2**zoom)
    result.stats = dict(source=source["name"], zoom=zoom, tiles=plan["count"], missing=missing,
                        resolution_m=round(resolution, 2))
    result.web = dict(tiles=dict(min_zoom=min_zoom, max_zoom=zoom, bounds=[west, south, east, north]))
    return result
