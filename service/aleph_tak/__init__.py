"""Aleph for TAK — capture service.

Draw an area in a TAK client, get back an offline TAK data package of it (imagery, elevation,
OSM features, street-level photos). The heavy lifting (tiling, merging, DTED/GeoTIFF/MBTiles
writing) lives here so the ATAK and CloudTAK plugins stay thin clients.
"""

from pathlib import Path

# The repo-root VERSION file is the single source of truth; install.sh copies it next to this
# package. Two candidates cover both layouts (repo checkout vs. installed /opt/aleph-tak/app).
_HERE = Path(__file__).resolve().parent


def _read_version():
    for candidate in (_HERE / "VERSION", _HERE.parent / "VERSION", _HERE.parent.parent / "VERSION"):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    return "0.0.0+unknown"


__version__ = _read_version()

# Bumped only on breaking changes to /api/v1. Clients read it from GET /api/v1/info and refuse
# to talk to a server whose major they don't know, instead of failing mid-capture.
API_VERSION = 1
