"""Writes atak/app/src/test/resources/aleph-package-dted1.zip — a package shaped exactly like the
service's, holding one level-1 DTED cell — so the ATAK plugin's Java DTED reader/merger is tested
against bytes this service really produces. Re-run after changing formats/dted.py:

    python -m tests.make_atak_fixture        (from service/)
"""
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from aleph_tak.formats import dted

OUT = Path(__file__).resolve().parents[2] / "atak/app/src/test/resources/aleph-package-dted1.zip"


def main():
    rows, cols = dted.shape(1, 39)
    heights = np.full((cols, rows), np.nan)
    heights[100:110, 200:210] = 200      # a 10×10 block of real posts…
    heights[105, 205] = -12              # …one below sea level (signed magnitude)
    with tempfile.TemporaryDirectory() as tmp:
        cell = Path(tmp) / "n39.dt1"
        dted.write(cell, 39, -90, 1, heights)
        nested = Path(tmp) / "fixture-dted.zip"
        with zipfile.ZipFile(nested, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(cell, "DTED/w090/n39.dt1")
            archive.writestr("DTED/../evil.dt1", b"must never be written")  # path-traversal probe
        with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as package:
            package.writestr("MANIFEST/manifest.xml", "<MissionPackageManifest version=\"2\"/>")
            package.write(nested, "elevation/fixture-dted.zip")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
