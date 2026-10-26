"""The TAK data package (mission package v2 zip) — the contract every client consumes.

ATAK and WinTAK import it with their built-in data-package import; TAK Server Data Sync can
push it unchanged. Layout:

    MANIFEST/manifest.xml          what to import, and photo ↔ marker links
    imagery/<name>.mbtiles         JPEG tile pyramid (ATAK native)
    imagery/<name>.tif             optional lossless COG (EPSG:3857)
    elevation/<name>-dted.zip      DTED/w089/n39.dt2 … (ignored by generic import; the ATAK
                                   plugin merges it into atak/DTED, filling voids only)
    elevation/<name>-elevation.tif Float32 GeoTIFF (ignored by TAK import; for GIS use)
    osm/<name>.kmz                 OSM features, one folder per layer
    photos/<uid>.cot + <uid>/…jpg  photo markers with their image attached
    aleph.json, ATTRIBUTION.txt    machine/human-readable provenance (ignored by import)

`ignore="true"` keeps a file in the package without asking TAK to import it.
"""

import hashlib
import uuid
import zipfile
from xml.sax.saxutils import quoteattr

from ..core.common import atomic_path

# Already-compressed payloads: deflating them again costs CPU on phones and saves nothing.
STORED = (".jpg", ".jpeg", ".png", ".zip", ".kmz", ".mbtiles", ".tif")


class Entry:
    def __init__(self, zip_path, source=None, data=None, *, ignore=False, uid=None):
        self.zip_path, self.source, self.data, self.ignore, self.uid = zip_path, source, data, ignore, uid


def manifest(name, package_uid, entries):
    lines = ['<MissionPackageManifest version="2">', "  <Configuration>",
             f'    <Parameter name="uid" value={quoteattr(package_uid)}/>',
             f'    <Parameter name="name" value={quoteattr(name)}/>',
             '    <Parameter name="onReceiveDelete" value="false"/>',
             "  </Configuration>", "  <Contents>"]
    for entry in entries:
        attrs = f'ignore="{str(entry.ignore).lower()}" zipEntry={quoteattr(entry.zip_path)}'
        if entry.uid:
            lines.append(f"    <Content {attrs}>")
            lines.append(f'      <Parameter name="uid" value={quoteattr(entry.uid)}/>')
            lines.append("    </Content>")
        else:
            lines.append(f"    <Content {attrs}/>")
    lines += ["  </Contents>", "</MissionPackageManifest>", ""]
    return "\n".join(lines)


def build(path, name, entries, *, package_uid=None):
    """Write the zip atomically; return its size and SHA-256 (clients verify resumed downloads)."""
    package_uid = package_uid or str(uuid.uuid4())
    with atomic_path(path) as temporary:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("MANIFEST/manifest.xml", manifest(name, package_uid, entries))
            for entry in entries:
                kind = zipfile.ZIP_STORED if entry.zip_path.lower().endswith(STORED) else zipfile.ZIP_DEFLATED
                if entry.data is not None:
                    archive.writestr(entry.zip_path, entry.data, compress_type=kind)
                else:
                    archive.write(entry.source, entry.zip_path, compress_type=kind)
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return dict(uid=package_uid, bytes=path.stat().st_size, sha256=digest.hexdigest())
