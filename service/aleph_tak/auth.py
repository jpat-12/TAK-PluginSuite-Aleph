"""Who may call the API, and links that carry their own authorization.

Three ways in, each for a reason:

* **Bearer tokens** (`Authorization: Bearer alt_<id>_<secret>`) for API clients. A `client`
  token is one person or device (ATAK); its owner is the token's name. A `proxy` token belongs
  to a server that authenticates its own users (the CloudTAK plugin's server half) and names
  the user per request in `X-Aleph-User`, so jobs stay per-user without each CloudTAK user
  needing an Aleph token.
* **Signed URLs** (`?exp=&sig=`) for things a browser or map library fetches without custom
  headers: map tiles, GeoJSON layers, package downloads. Each signature covers one path and
  expires; it grants nothing else.
* **Admin session** for /admin, opened by a local admin password or by a single-sign-on link
  minted by the infra-TAK console hook (so the console's own login is the gate).

Only token *hashes* are stored; the plaintext is shown once at creation.
"""

import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from .core.common import now, write_json

TOKEN_RE = re.compile(r"^alt_([0-9a-f]{12})_([0-9A-Za-z_-]{32,})$")
ROLES = ("client", "proxy")
USER_RE = re.compile(r"^[\w .@:+-]{1,100}$")


def _digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


class Tokens:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.items = self._load()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("tokens", [])
        except FileNotFoundError:
            return []

    def _save(self):
        write_json(self.path, {"tokens": self.items})

    def create(self, name, role="client"):
        name = (name or "").strip()
        if not USER_RE.match(name):
            raise ValueError("Token name: 1–100 letters, digits, spaces or . @ : + - _")
        if role not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        identity, secret = secrets.token_hex(6), secrets.token_urlsafe(32)
        with self.lock:
            self.items.append(dict(id=identity, name=name, role=role, hash=_digest(secret),
                                   created_at=now(), last_used_at=None, revoked=False))
            self._save()
        return f"alt_{identity}_{secret}"

    def revoke(self, identity):
        with self.lock:
            for item in self.items:
                if item["id"] == identity:
                    item["revoked"] = True
                    self._save()
                    return True
        return False

    def verify(self, token):
        match = TOKEN_RE.match(token or "")
        if not match:
            return None
        identity, secret = match.groups()
        with self.lock:
            for item in self.items:
                if item["id"] == identity and not item.get("revoked"):
                    if hmac.compare_digest(item["hash"], _digest(secret)):
                        # Coarse last-use stamp; skip the write when it's already today.
                        stamp = now()
                        if (item.get("last_used_at") or "")[:10] != stamp[:10]:
                            item["last_used_at"] = stamp
                            self._save()
                        return item
                    return None
        return None

    def public(self):
        return [{k: v for k, v in item.items() if k != "hash"} for item in self.items]


def identify(tokens, headers):
    """Return (owner, role) for a bearer request, or raise AuthError."""
    header = headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthError("Missing bearer token.")
    item = tokens.verify(header[7:].strip())
    if item is None:
        raise AuthError("Invalid or revoked token.")
    if item["role"] == "proxy":
        user = (headers.get("X-Aleph-User") or "").strip()
        if not USER_RE.match(user):
            raise AuthError("A proxy token must name the user in X-Aleph-User.", 400)
        # Namespaced so a CloudTAK user can never collide with an ATAK token's name.
        return f"{item['name']}:{user}", "proxy"
    return item["name"], "client"


class Signer:
    def __init__(self, key):
        self.key = key.encode()

    def sign(self, path, lifetime_s):
        expires = int(time.time() + lifetime_s)
        return expires, self._mac(path, expires)

    def _mac(self, path, expires):
        return hmac.new(self.key, f"{path}\n{expires}".encode(), hashlib.sha256).hexdigest()[:40]

    def verify(self, path, expires, signature):
        try:
            expires = int(expires)
        except (TypeError, ValueError):
            return False
        return expires >= time.time() and hmac.compare_digest(self._mac(path, expires), signature or "")

    def query(self, path, lifetime_s):
        expires, signature = self.sign(path, lifetime_s)
        return f"exp={expires}&sig={signature}"


def sso_signature(key, user, expires):
    """Shared with infratak/aleph_infratak.py, which mints these links inside the console."""
    return hmac.new(key.encode(), f"sso\n{user}\n{int(expires)}".encode(), hashlib.sha256).hexdigest()
