"""MBTiles 1.3 writer. ATAK 5.6 reads MBTiles natively (MbTilesFileType), and JPEG tiles make
it ~6× smaller than Aleph's lossless COG, so it's the default imagery format in packages.

MBTiles rows are TMS (origin bottom-left); our tiles are XYZ (origin top-left) — flipped here.
"""

import sqlite3

from ..core.common import atomic_path


def write(path, tiles, metadata):
    """tiles: iterable of (zoom, x, y, bytes) in XYZ. metadata: MBTiles metadata name → value."""
    with atomic_path(path) as temporary:
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                "CREATE TABLE metadata (name TEXT, value TEXT);"
                "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);"
            )
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", [(k, str(v)) for k, v in metadata.items()])
            connection.executemany(
                "INSERT INTO tiles VALUES (?, ?, ?, ?)",
                ((zoom, x, (1 << zoom) - 1 - y, sqlite3.Binary(data)) for zoom, x, y, data in tiles),
            )
            connection.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
            connection.commit()
        finally:
            connection.close()


def read_tile(path, zoom, x, y):
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                                 (zoom, x, (1 << zoom) - 1 - y)).fetchone()
        return None if row is None else bytes(row[0])
    finally:
        connection.close()
