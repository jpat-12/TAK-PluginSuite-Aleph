"""Output formats are the contract with TAK clients — byte layouts are tested exactly."""

import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from aleph_tak.formats import datapackage, dted, geotiff, kml, mbtiles
from aleph_tak.formats.cot import photo_marker


class DTEDTests(unittest.TestCase):
    def test_cell_shape_follows_latitude_zones(self):
        self.assertEqual(dted.shape(2, 39), (3601, 3601))     # zone I: 1" × 1"
        self.assertEqual(dted.shape(2, 55), (3601, 1801))     # zone II: lon 2"
        self.assertEqual(dted.shape(1, 39), (1201, 1201))     # level 1: 3"
        self.assertEqual(dted.shape(2, -50), (3601, 3601))    # s50 cell spans −50…−49 → zone I
        self.assertEqual(dted.shape(2, -51), (3601, 1801))

    def test_paths_match_atak_dted_tree(self):
        self.assertEqual(dted.cell_path(39, -90, 2), "w090/n39.dt2")
        self.assertEqual(dted.cell_path(-1, 5, 1), "e005/s01.dt1")

    def test_header_fields_sit_at_spec_offsets(self):
        raw = dted.headers(39, -90, 2).decode("ascii")
        uhl, dsi = raw[:80], raw[80:728]
        self.assertEqual(uhl[:4], "UHL1")
        self.assertEqual(uhl[4:12], "0900000W")
        self.assertEqual(uhl[12:20], "0390000N")
        self.assertEqual((uhl[20:24], uhl[24:28]), ("0010", "0010"))
        self.assertEqual((uhl[47:51], uhl[51:55]), ("3601", "3601"))
        self.assertEqual(dsi[:3], "DSI")
        self.assertEqual(dsi[59:64], "DTED2")
        self.assertEqual(dsi[185:194], "390000.0N")
        self.assertEqual(dsi[194:204], "0900000.0W")
        self.assertEqual(dsi[273:281], "00100010")
        self.assertEqual(dsi[281:289], "36013601")
        self.assertEqual(raw[728:731], "ACC")
        self.assertEqual(len(raw), dted.HEADER_BYTES)

    def test_round_trip_with_voids_negatives_and_checksums(self):
        rows, cols = dted.shape(1, 39)
        heights = np.full((cols, rows), np.nan)
        heights[10, 20] = 187.4
        heights[11, 20] = -12          # below sea level: signed magnitude, not two's complement
        heights[12, 21] = 32767
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "n39.dt1"
            dted.write(path, 39, -90, 1, heights)
            self.assertEqual(path.stat().st_size, dted.HEADER_BYTES + cols * (12 + rows * 2))
            raw = path.read_bytes()
            post = dted.HEADER_BYTES + 11 * (12 + rows * 2) + 8 + 20 * 2
            self.assertEqual(raw[post:post + 2], bytes([0x80, 12]))
            header, back = dted.read(path)
        self.assertEqual((header["profiles"], header["posts"]), (cols, rows))
        self.assertEqual(back[10, 20], 187)
        self.assertEqual(back[11, 20], -12)
        self.assertEqual(back[12, 21], 32767)
        self.assertEqual(back[0, 0], dted.VOID)

    def test_wrong_shape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            dted.write(Path(tmp) / "x.dt2", 39, -90, 2, np.zeros((10, 10)))

    def test_cells_for_bbox_edges(self):
        self.assertEqual(dted.cells_for(39.2, -89.8, 39.4, -89.6), [(39, -90)])
        self.assertEqual(len(dted.cells_for(39.9, -90.1, 40.1, -89.9)), 4)
        self.assertEqual(dted.cells_for(39.5, -90.0, 40.0, -89.5), [(39, -90)])


class GeoTIFFTests(unittest.TestCase):
    def test_round_trip_and_georeferencing(self):
        heights = np.arange(40 * 33, dtype=np.float32).reshape(40, 33)
        heights[0, 0] = np.nan
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.tif"
            geotiff.write(path, heights, -89.7, 39.8, 1 / 3600, 1 / 3600)
            back, tags = geotiff.read(path)
        self.assertEqual(back.shape, (40, 33))
        self.assertEqual(back[0, 0], geotiff.NODATA)
        np.testing.assert_array_equal(back[1:], heights[1:])
        self.assertAlmostEqual(tags[33922][3], -89.7 - 0.5 / 3600)   # pixel-is-area corner
        self.assertAlmostEqual(tags[33922][4], 39.8 + 0.5 / 3600)
        self.assertIn(4326, tags[34735])
        self.assertEqual(tags[42113].rstrip(b"\0"), b"-32767")


class MBTilesTests(unittest.TestCase):
    def test_xyz_rows_are_stored_as_tms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.mbtiles"
            mbtiles.write(path, [(17, 32895, 49716, b"jpeg")], {"format": "jpg", "minzoom": 17})
            connection = sqlite3.connect(path)
            row = connection.execute("SELECT zoom_level, tile_column, tile_row FROM tiles").fetchone()
            meta = dict(connection.execute("SELECT name, value FROM metadata"))
            connection.close()
            self.assertEqual(row, (17, 32895, 2**17 - 1 - 49716))
            self.assertEqual(meta["format"], "jpg")
            self.assertEqual(mbtiles.read_tile(path, 17, 32895, 49716), b"jpeg")


class PackageTests(unittest.TestCase):
    def test_manifest_lists_entries_with_ignore_and_uid_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.mbtiles"
            src.write_bytes(b"x" * 100)
            entries = [datapackage.Entry("imagery/a.mbtiles", src),
                       datapackage.Entry("photos/p1.cot", data="<event/>", uid="p1"),
                       datapackage.Entry("photos/p1/1.jpg", data=b"jpg", uid="p1"),
                       datapackage.Entry("aleph.json", data="{}", ignore=True)]
            info = datapackage.build(Path(tmp) / "pkg.zip", 'Test & "capture"', entries, package_uid="uid-1")
            with zipfile.ZipFile(Path(tmp) / "pkg.zip") as archive:
                names = archive.namelist()
                manifest = ET.fromstring(archive.read("MANIFEST/manifest.xml"))
                self.assertEqual(archive.getinfo("imagery/a.mbtiles").compress_type, zipfile.ZIP_STORED)
        self.assertEqual(names[0], "MANIFEST/manifest.xml")
        self.assertEqual(len(info["sha256"]), 64)
        params = {p.get("name"): p.get("value") for p in manifest.find("Configuration")}
        self.assertEqual(params, {"uid": "uid-1", "name": 'Test & "capture"', "onReceiveDelete": "false"})
        contents = manifest.find("Contents")
        by_entry = {c.get("zipEntry"): c for c in contents}
        self.assertEqual(set(by_entry), {"imagery/a.mbtiles", "photos/p1.cot", "photos/p1/1.jpg", "aleph.json"})
        self.assertEqual(by_entry["aleph.json"].get("ignore"), "true")
        self.assertEqual(by_entry["photos/p1/1.jpg"].find("Parameter").get("value"), "p1")


class KMLAndCoTTests(unittest.TestCase):
    def test_kml_is_well_formed_with_folders_per_layer(self):
        features = [
            dict(type="Feature", geometry=dict(type="LineString", coordinates=[[-89.6, 39.8], [-89.5, 39.8]]),
                 properties=dict(layer="trails", name="A <trail>", kind="highway=path")),
            dict(type="Feature", geometry=dict(type="Polygon", coordinates=[[[0, 0], [1, 0], [1, 1], [0, 0]]]),
                 properties=dict(layer="buildings", name="", kind="building=yes")),
        ]
        root = ET.fromstring(kml.document(features, "T", "D"))
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        folders = [f.find("k:name", ns).text for f in root.iter("{http://www.opengis.net/kml/2.2}Folder")]
        self.assertEqual(folders, ["Trails & tracks", "Buildings"])

    def test_photo_marker_is_quick_pic_cot(self):
        event = ET.fromstring(photo_marker("aleph-photo-1", 39.8, -89.6, "Photo", "by <x>"))
        self.assertEqual(event.get("type"), "b-i-x-i")
        self.assertEqual(event.find("point").get("lat"), "39.8000000")
        self.assertEqual(event.find("detail/remarks").text, "by <x>")


if __name__ == "__main__":
    unittest.main()
