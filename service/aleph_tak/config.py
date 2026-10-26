"""Service configuration: one JSON file of settings plus one of secrets, both in the data dir.

Settings are editable from the admin page; secrets (signing key, admin password hash) are
generated once and never leave the server. Loading spreads the defaults under whatever is on
disk, so a config written by an older version gains new keys instead of failing.
"""

import copy
import json
import os
import secrets
from pathlib import Path

from .core.common import write_json

DEFAULT_DATA_DIR = "/opt/aleph-tak/data"

DEFAULTS = {
    # Absolute base URL clients reach this service at (https://aleph.<fqdn>). Signed links in
    # job responses are built from it; empty means "relative links" (fine behind one proxy).
    "public_url": "",
    "listen": "127.0.0.1:8781",
    "max_area_km2": 25.0,
    "job_ttl_hours": 72,
    "max_concurrent_jobs": 1,
    "imagery": {
        "source": "usgs-naip",
        "zoom": 17,
        "max_zoom": 18,
        # Extra formats on top of MBTiles; "geotiff" adds a lossless COG (much bigger).
        "extra_formats": [],
        # Only used when source == "custom": an imagery service CAP is licensed to cache.
        "custom": {"kind": "xyz", "url": "", "attribution": "", "max_zoom": 19},
    },
    "elevation": {"zoom": 13, "dted_level": 2},
    "osm": {"enabled": True},
    "photos": {"mapillary_token": "", "limit": 200},
    # Public Photon is fair-use only (plan: self-host for production).
    "geocoder_url": "https://photon.komoot.io",
    # Link lifetime for tile/GeoJSON/package URLs handed to browsers.
    "signed_url_hours": 12,
}

# Settings the admin page may change; everything else is install-time only.
EDITABLE = ("public_url", "max_area_km2", "job_ttl_hours", "imagery", "elevation", "osm", "photos",
            "geocoder_url", "signed_url_hours")


def merge(defaults, override):
    """Defaults first, then saved values, one level of nesting deep (all our sections are flat)."""
    result = copy.deepcopy(defaults)
    for key, value in (override or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir or os.environ.get("ALEPH_DATA_DIR") or DEFAULT_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.data_dir / "config.json"
        self.secrets_path = self.data_dir / "secrets.json"
        self.settings = merge(DEFAULTS, self._read(self.settings_path))
        self.secrets = self._load_secrets()

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except ValueError as error:
            raise ValueError(f"{path} is not valid JSON: {error}") from error

    def _load_secrets(self):
        saved = self._read(self.secrets_path)
        changed = False
        # console_sso_key is read (as root) by the infra-TAK console hook to mint admin
        # single-sign-on links, so the console's own login gates this admin page.
        for key in ("signing_key", "session_key", "console_sso_key"):
            if not saved.get(key):
                saved[key] = secrets.token_hex(32)
                changed = True
        if changed:
            write_json(self.secrets_path, saved)
        try:
            os.chmod(self.secrets_path, 0o600)
        except OSError:
            pass  # Windows dev boxes; production is Linux
        return saved

    def __getitem__(self, key):
        return self.settings[key]

    @property
    def jobs_dir(self):
        return self.data_dir / "jobs"

    @property
    def cache_dir(self):
        # Shared across jobs: Geofabrik region extracts are hundreds of MB and reused for weeks.
        return self.data_dir / "cache"

    def update(self, values):
        unknown = set(values) - set(EDITABLE)
        if unknown:
            raise ValueError(f"Not editable: {', '.join(sorted(unknown))}")
        self.settings = merge(self.settings, values)
        self.save()

    def save(self):
        write_json(self.settings_path, self.settings)

    def save_secrets(self):
        write_json(self.secrets_path, self.secrets)
