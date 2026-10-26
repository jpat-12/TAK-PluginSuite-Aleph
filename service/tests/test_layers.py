"""Layers end to end with the network replaced by synthetic tiles."""

import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from aleph_tak.config import DEFAULTS, merge
from aleph_tak.core.geo import corners
from aleph_tak.formats import dted, geotiff, mbtiles
from aleph_tak.layers import Context, elevation, imagery, osm

# ~1.1 km × 0.85 km in Springfield, IL.
AREA = corners((39.795, -89.655, 39.805, -89.645))


def terrarium(height):
    value = height + 32768
    r, g = int(value // 256), int(value % 256)
    b = int(round((value - int(value)) * 256))
    with BytesIO() as buffer:
        Image.new("RGB", (256, 256), (r, g, b)).save(buffer, "PNG")
        return buffer.getvalue()


def jpeg(color):
    with BytesIO() as buffer:
        Image.new("RGB", (256, 256), color).save(buffer, "JPEG")
        return buffer.getvalue()


def fake_fetch(payload, missing_every=None):
    def fetch(client, addresses, workers):
        for i, _ in enumerate(addresses):
            yield None if missing_every and i % missing_every == 0 else payload
    return fetch


def context(tmp, **options):
    opts = dict(imagery_zoom=16, imagery_formats=["mbtiles"], elevation_zoom=12, dted_level=1)
    opts.update(options)
    return Context(job_dir=Path(tmp), name="test", polygon=AREA, options=opts, settings=merge(DEFAULTS, {}),
                   client=None, progress=lambda *a, **k: None)


class ElevationTests(unittest.TestCase):
    def test_terrarium_decoding(self):
        self.assertAlmostEqual(float(elevation.decode_terrarium(terrarium(187.5))[0, 0]), 187.5, places=2)
        self.assertAlmostEqual(float(elevation.decode_terrarium(terrarium(-10))[5, 5]), -10, places=2)

    def test_dted_holds_heights_inside_the_bbox_and_voids_outside(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(elevation, "fetch_each", fake_fetch(terrarium(180))):
            result = elevation.run(context(tmp))
            dted_zip = Path(tmp) / "out" / "test-dted.zip"
            with zipfile.ZipFile(dted_zip) as archive:
                self.assertEqual(archive.namelist(), ["DTED/w090/n39.dt1"])
                archive.extractall(tmp)
            header, posts = dted.read(Path(tmp) / "DTED/w090/n39.dt1")
            heights, _ = geotiff.read(Path(tmp) / "out" / "test-elevation.tif")
        self.assertEqual(header["lon_origin"], "0900000W")
        filled = posts[posts != dted.VOID]
        self.assertTrue(filled.size > 100)
        self.assertTrue(np.all(filled == 180))
        self.assertEqual(posts[0, 0], dted.VOID)                        # cell corner, far outside the area
        self.assertTrue(np.allclose(heights, 180))
        self.assertEqual(result.stats["dted_cells"], ["w090/n39.dt1"])
        self.assertEqual([e.zip_path for e in result.entries], ["elevation/test-dted.zip", "elevation/test-elevation.tif"])
        # Neither is imported generically: DTED is merged by the ATAK plugin (never clobbering a
        # device's complete cells), and TAK would mistake the Float32 GeoTIFF for imagery.
        self.assertTrue(result.entries[0].ignore)
        self.assertTrue(result.entries[1].ignore)

    def test_resume_skips_downloaded_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(elevation, "fetch_each", fake_fetch(terrarium(50))):
                elevation.run(context(tmp))
            calls = []

            def counting_fetch(client, addresses, workers):
                calls.extend(addresses)
                return iter(())
            with mock.patch.object(elevation, "fetch_each", counting_fetch):
                elevation.run(context(tmp))
        self.assertEqual(calls, [])


class ImageryTests(unittest.TestCase):
    def test_mbtiles_pyramid_and_partial_overviews(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(imagery, "fetch_each", fake_fetch(jpeg((10, 120, 30)), 3)):
            result = imagery.run(context(tmp))
            path = Path(tmp) / "out" / "test.mbtiles"
            info = result.web["tiles"]
            self.assertEqual((info["min_zoom"], info["max_zoom"]), (10, 16))
            import sqlite3
            connection = sqlite3.connect(path)
            zooms = [z for (z,) in connection.execute("SELECT DISTINCT zoom_level FROM tiles ORDER BY 1")]
            meta = dict(connection.execute("SELECT name, value FROM metadata"))
            connection.close()
            # Lowest overview has gaps underneath → stored as PNG so the gaps stay transparent.
            top = next(imagery._tiles_at(Path(tmp) / "work/imagery/tiles", 10))
            self.assertIsNotNone(mbtiles.read_tile(path, 10, *top))
        self.assertEqual(zooms, list(range(10, 17)))
        self.assertEqual(meta["maxzoom"], "16")
        self.assertTrue(result.warnings)  # every third tile "missing"

    def test_whole_area_missing_fails_the_layer(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(imagery, "fetch_each", fake_fetch(None)):
            with self.assertRaises(Exception):
                imagery.run(context(tmp))

    def test_flaky_source_fails_softly_then_retry_fills_gaps(self):
        flaky = fake_fetch(jpeg((1, 2, 3)))

        def one_bad_tile(client, addresses, workers):
            for i, data in enumerate(flaky(client, addresses, workers)):
                yield OSError("HTTP 502") if i == 0 else data
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(imagery, "fetch_each", one_bad_tile):
                first = imagery.run(context(tmp))
            self.assertTrue(any("retry" in w for w in first.warnings))
            fetched = []

            def record(client, addresses, workers):
                fetched.extend(addresses)
                return flaky(client, addresses, workers)
            with mock.patch.object(imagery, "fetch_each", record):
                second = imagery.run(context(tmp))
        self.assertEqual(len(fetched), 1)          # only the failed tile is requested again
        self.assertFalse(second.warnings)

    def test_mostly_failing_source_fails_the_layer(self):
        def all_bad(client, addresses, workers):
            for _ in addresses:
                yield OSError("HTTP 502")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(imagery, "fetch_each", all_bad):
            with self.assertRaisesRegex(OSError, "Retry the capture"):
                imagery.run(context(tmp))

    def test_optional_cog_reuses_aleph_writer(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(imagery, "fetch_each", fake_fetch(jpeg((200, 200, 200)))):
            result = imagery.run(context(tmp, imagery_formats=["mbtiles", "geotiff"]))
            cog = Path(tmp) / "out" / "test.tif"
            self.assertTrue(cog.read_bytes()[:4] in (b"II*\0", b"II+\0"))
        self.assertEqual([e.zip_path for e in result.entries], ["imagery/test.mbtiles", "imagery/test.tif"])


class OSMTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(osm.classify_way({"highway": "track"}, False), "trails")
        self.assertEqual(osm.classify_way({"building": "yes"}, True), "buildings")
        self.assertIsNone(osm.classify_way({"building": "yes"}, False))
        self.assertEqual(osm.classify_way({"power": "line"}, False), "power")
        self.assertEqual(osm.classify_node({"aeroway": "helipad"}), "aero")
        self.assertIsNone(osm.classify_node({"amenity": "bench"}))   # unnamed POIs are noise

    def test_lines_are_clipped_at_the_area_edge(self):
        road = dict(type="way", id=1, tags={"highway": "residential", "name": "Main"}, nodes=[1, 2],
                    points=[(39.800, -89.700), (39.800, -89.600)])
        outside = dict(type="way", id=2, tags={"highway": "residential"}, nodes=[3, 4],
                       points=[(39.900, -89.700), (39.900, -89.600)])
        place = dict(type="node", id=5, tags={"name": "Fire station", "amenity": "fire_station"}, center=(39.8, -89.65))
        features = osm.to_features([road, outside, place], AREA)
        self.assertEqual([f["properties"]["layer"] for f in features], ["roads_minor", "places"])
        line = features[0]["geometry"]["coordinates"]
        self.assertAlmostEqual(line[0][0], -89.655, places=6)
        self.assertAlmostEqual(line[-1][0], -89.645, places=6)


if __name__ == "__main__":
    unittest.main()
