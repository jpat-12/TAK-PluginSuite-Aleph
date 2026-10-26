#!/usr/bin/env python3
"""Keep Aleph's site block in infra-TAK's Caddyfile — on any infra-TAK version.

infra-TAK rewrites /etc/caddy/Caddyfile from scratch whenever a module is deployed, but since
v0.2.0 it carries everything below "# --- User-added blocks (do not remove) ---" over into the
new file. So the block goes below that marker (the marker is added if missing). On v0.1.x,
which has no marker, the aleph-tak-heal.path unit re-runs `ensure` after every rewrite.

Stdlib only: this runs under the system python3, and inside the console process (hook), never
in Aleph's venv.

    aleph_caddy.py ensure  [--reload] [--caddyfile F] [--console-dir D] [--aleph-data D] [--domain H]
    aleph_caddy.py remove  [--reload] [--caddyfile F]
    aleph_caddy.py host    [--console-dir D] [--aleph-data D] [--domain H]
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

BEGIN = "# >>> aleph-tak (managed by InfraTAK-Plugin-Aleph — edits here are overwritten)"
END = "# <<< aleph-tak"
USER_BLOCKS_MARKER = "# --- User-added blocks (do not remove) ---"
DEFAULT_CADDYFILE = "/etc/caddy/Caddyfile"
DEFAULT_ALEPH_DATA = "/opt/aleph-tak/data"
CONSOLE_DIRS = ("/opt/infra-TAK", "/opt/infra-tak", "/root/infra-TAK", "/root/infra-tak")


def find_console_dir():
    for directory in CONSOLE_DIRS + (os.path.expanduser("~/infra-TAK"), os.path.expanduser("~/infra-tak")):
        if os.path.isfile(os.path.join(directory, "app.py")):
            return directory
    return None


def read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {}


def aleph_host(console_dir=None, aleph_data=DEFAULT_ALEPH_DATA, override=None):
    """Same rule as infra-TAK's _get_service_domain: `aleph_domain` override (a bare label gets
    the base FQDN appended), else aleph.<fqdn>."""
    settings = read_json(os.path.join(console_dir, ".config", "settings.json")) if console_dir else {}
    fqdn = (settings.get("fqdn") or "").strip()
    custom = (override or settings.get("aleph_domain") or "").strip()
    if custom:
        return custom if "." in custom or not fqdn else f"{custom}.{fqdn}"
    if fqdn:
        return f"aleph.{fqdn}"
    public = read_json(os.path.join(aleph_data, "config.json")).get("public_url", "")
    return public.split("://", 1)[-1].strip("/") or None


def upstream(aleph_data=DEFAULT_ALEPH_DATA):
    return read_json(os.path.join(aleph_data, "config.json")).get("listen") or "127.0.0.1:8781"


def block(host, target):
    # Not behind Authentik forward_auth on purpose: ATAK authenticates with Aleph bearer tokens,
    # browsers with signed links, and /admin with the console's SSO — forward_auth would lock
    # out the phones. Long timeouts: package downloads over field LTE can take many minutes.
    return "\n".join([
        BEGIN,
        f"{host} {{",
        "    encode gzip",
        "    request_body {",
        "        max_size 4MB",
        "    }",
        f"    reverse_proxy {target} {{",
        "        transport http {",
        "            read_timeout 1h",
        "            write_timeout 1h",
        "        }",
        "    }",
        "}",
        END,
    ])


def strip(text):
    while BEGIN in text and END in text:
        start = text.index(BEGIN)
        stop = text.index(END, start) + len(END)
        text = text[:start].rstrip("\n") + "\n" + text[stop:].lstrip("\n")
    return text


def ensure(text, new_block):
    text = strip(text).rstrip("\n")
    if USER_BLOCKS_MARKER not in text:
        text += "\n\n" + USER_BLOCKS_MARKER
    return text + "\n\n" + new_block + "\n"


def _validate():
    caddy = shutil.which("caddy")
    if not caddy:
        return True, "caddy binary not found; skipped validation"
    result = subprocess.run([caddy, "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
                            capture_output=True, text=True, timeout=60)
    return result.returncode == 0, (result.stdout + result.stderr)[-2000:]


def write_and_reload(path, new_text, reload):
    with open(path, encoding="utf-8") as stream:
        old_text = stream.read()
    if old_text == new_text:
        return "unchanged"
    backup = f"{path}.aleph-bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(new_text)
    if not reload:
        return "written"
    ok, output = _validate()
    if ok:
        ok = subprocess.run(["systemctl", "reload", "caddy"], capture_output=True, timeout=60).returncode == 0
        output = output if ok else "systemctl reload caddy failed"
    if not ok:
        shutil.copy2(backup, path)
        subprocess.run(["systemctl", "reload", "caddy"], capture_output=True, timeout=60)
        raise RuntimeError(f"Caddy rejected the Aleph block; restored {backup}.\n{output}")
    return "reloaded"


def update_public_url(aleph_data, host):
    """Point the service's signed links at the public host, unless an admin already chose one."""
    path = os.path.join(aleph_data, "config.json")
    config = read_json(path)
    if config.get("public_url") or not host or not os.path.isdir(aleph_data):
        return
    config["public_url"] = f"https://{host}"
    stat = os.stat(aleph_data)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2)
    try:
        os.chown(path, stat.st_uid, stat.st_gid)
    except (AttributeError, PermissionError):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("ensure", "remove", "host"))
    parser.add_argument("--caddyfile", default=DEFAULT_CADDYFILE)
    parser.add_argument("--console-dir", default=None)
    parser.add_argument("--aleph-data", default=DEFAULT_ALEPH_DATA)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    console_dir = args.console_dir or find_console_dir()
    host = aleph_host(console_dir, args.aleph_data, args.domain)

    if args.action == "host":
        print(host or "")
        return 0 if host else 1
    if not os.path.isfile(args.caddyfile):
        print(f"[aleph-tak] {args.caddyfile} not found — deploy Caddy in infra-TAK first, then re-run.")
        return 2
    with open(args.caddyfile, encoding="utf-8") as stream:
        text = stream.read()
    if args.action == "remove":
        print(f"[aleph-tak] caddy: {write_and_reload(args.caddyfile, strip(text), args.reload)}")
        return 0
    if not host:
        print("[aleph-tak] No base FQDN in infra-TAK settings and no --domain; set one on the Caddy page.")
        return 3
    print(f"[aleph-tak] caddy {host}: {write_and_reload(args.caddyfile, ensure(text, block(host, upstream(args.aleph_data))), args.reload)}")
    update_public_url(args.aleph_data, host)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"[aleph-tak] {error}", file=sys.stderr)
        sys.exit(1)
