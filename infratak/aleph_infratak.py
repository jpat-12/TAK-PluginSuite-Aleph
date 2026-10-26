"""Aleph for TAK inside the infra-TAK console — attached at runtime, on any infra-TAK version.

attach() receives the console's freshly loaded `app` module and adds, *if the hook point
exists in this version*:

    app + login_required   →  /aleph status page and /aleph/admin (single sign-on to Aleph admin)
    detect_modules         →  an "Aleph for TAK" module card on the console dashboard
    render_sidebar         →  an "Aleph" link in the left nav
    SERVICE_DOMAIN_DEFAULTS→  'aleph' → aleph.<fqdn> (so infra-TAK's domain rules apply)
    generate_caddyfile     →  re-adds Aleph's site block whenever infra-TAK rewrites the Caddyfile

Every hook point above exists unchanged from infra-TAK v0.1.0 through the current dev branch
(checked against all 126 tags); anything missing in some future version is skipped, not fatal.
Each piece is wrapped separately so one failure can't take the others — or the console — down.

Runs inside the console's own Python: stdlib only, plus Flask objects the console hands us.
"""

import html
import json
import os
import subprocess
import sys
import time
import urllib.request

ALEPH_HOME = os.environ.get("ALEPH_HOME", "/opt/aleph-tak")
DATA_DIR = os.path.join(ALEPH_HOME, "data")
UNIT = "/etc/systemd/system/aleph-tak.service"
BIN_DIR = os.path.join(ALEPH_HOME, "bin")

_status_cache = {"at": 0.0, "value": None}


def _log(message):
    print(f"[aleph-tak] {message}", file=sys.stderr, flush=True)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {}


def _service_status():
    """(installed, running, detail) — cached 10 s; detect_modules runs on every page load."""
    if time.monotonic() - _status_cache["at"] < 10 and _status_cache["value"]:
        return _status_cache["value"]
    installed = os.path.exists(UNIT)
    running, detail = False, {}
    if installed:
        listen = _read_json(os.path.join(DATA_DIR, "config.json")).get("listen") or "127.0.0.1:8781"
        try:
            with urllib.request.urlopen(f"http://{listen}/admin/api/status", timeout=1.5) as response:
                detail = json.loads(response.read())
                running = True
        except Exception:
            running = False
    _status_cache.update(at=time.monotonic(), value=(installed, running, detail))
    return installed, running, detail


def _public_url():
    return (_read_json(os.path.join(DATA_DIR, "config.json")).get("public_url") or "").rstrip("/")


def module_entry():
    installed, running, _ = _service_status()
    return {"name": "Aleph for TAK", "installed": installed, "running": running,
            "description": "Capture an area as an offline TAK data package (imagery, DTED, OSM, photos)",
            "icon": "\U0001F6F0️", "route": "/aleph", "priority": 14}


# --- individual hook points ---------------------------------------------------------------

def _wrap_detect_modules(g):
    original = g["detect_modules"]
    if getattr(original, "_aleph", False):
        return
    def detect_modules(*args, **kwargs):
        modules = original(*args, **kwargs)
        try:
            modules["aleph"] = module_entry()
            modules = dict(sorted(modules.items(), key=lambda item: item[1].get("priority", 99)))
        except Exception as error:
            _log(f"module card skipped: {error!r}")
        return modules
    detect_modules._aleph = True
    g["detect_modules"] = detect_modules


def _wrap_render_sidebar(g):
    original = g["render_sidebar"]
    if getattr(original, "_aleph", False):
        return
    def render_sidebar(modules, active_path, *args, **kwargs):
        markup = original(modules, active_path, *args, **kwargs)
        try:
            if (modules or {}).get("aleph", {}).get("installed") and "</nav>" in markup and 'href="/aleph"' not in markup:
                active = " active" if (active_path or "").strip("/").startswith("aleph") else ""
                link = (f'<a href="/aleph" class="nav-item{active}" title="Aleph for TAK">'
                        '<span class="nav-icon material-symbols-outlined">satellite_alt</span>Aleph</a>\n')
                cut = markup.rindex("</nav>")
                markup = markup[:cut] + "  " + link + markup[cut:]
        except Exception as error:
            _log(f"sidebar link skipped: {error!r}")
        return markup
    render_sidebar._aleph = True
    g["render_sidebar"] = render_sidebar


def _wrap_generate_caddyfile(g):
    original = g["generate_caddyfile"]
    if getattr(original, "_aleph", False):
        return
    def generate_caddyfile(*args, **kwargs):
        result = original(*args, **kwargs)
        try:
            # infra-TAK reloads Caddy itself right after generating; we only write the file.
            subprocess.run([sys.executable, os.path.join(BIN_DIR, "aleph_caddy.py"), "ensure"],
                           capture_output=True, timeout=30)
        except Exception as error:
            _log(f"Caddy block not re-added (aleph-tak-heal will retry): {error!r}")
        return result
    generate_caddyfile._aleph = True
    g["generate_caddyfile"] = generate_caddyfile


PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Aleph for TAK — infra-TAK</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">
<style>
:root{--bg-deep:#080b14;--bg-surface:#0f1219;--bg-card:#161b26;--border:#1e2736;--border-hover:#2a3548;--text-primary:#f1f5f9;--text-secondary:#cbd5e1;--text-dim:#94a3b8;--cyan:#06b6d4;--green:#10b981;--red:#ef4444;--yellow:#eab308}
*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg-deep);color:var(--text-primary);font-family:'DM Sans',sans-serif;min-height:100vh;display:flex}
.sidebar{width:220px;min-width:220px;background:var(--bg-surface);border-right:1px solid var(--border);padding:24px 0;display:flex;flex-direction:column}
.material-symbols-outlined{font-family:'Material Symbols Outlined';font-size:20px;line-height:1;-webkit-font-smoothing:antialiased}
.sidebar-logo{padding:0 20px 24px;border-bottom:1px solid var(--border);margin-bottom:16px}.sidebar-logo span{font-size:15px;font-weight:700}.sidebar-logo small{display:block;font-size:10px;color:var(--text-dim);font-family:'JetBrains Mono',monospace}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 20px;color:var(--text-secondary);text-decoration:none;font-size:13px;font-weight:500;border-left:2px solid transparent}
.nav-item:hover{color:var(--text-primary);background:rgba(255,255,255,.03)}.nav-item.active{color:var(--cyan);background:rgba(6,182,212,.06);border-left-color:var(--cyan)}
.nav-icon{font-size:15px;width:18px;text-align:center}.main{flex:1;min-width:0;padding:32px;overflow-y:auto}
h1{font-size:22px}.sub{color:var(--text-secondary);font-size:13px;margin:4px 0 24px}
.banner{display:flex;align-items:center;gap:10px;padding:14px 18px;border-radius:10px;margin-bottom:20px;font-size:13px}
.ok{background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);color:var(--green)}.bad{background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.25);color:var(--red)}
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.item{background:#0a0e1a;border-radius:8px;padding:12px 14px}
.label{font-size:11px;color:var(--text-dim);text-transform:uppercase;margin-bottom:3px}.value{font-family:'JetBrains Mono',monospace;font-size:13px;word-break:break-all}
.btn{display:inline-block;padding:10px 18px;border-radius:8px;background:var(--cyan);color:#001;font-weight:600;text-decoration:none;font-size:13px;margin-right:8px}
.dim{color:var(--text-dim);font-size:12px;margin-top:12px}code{font-family:'JetBrains Mono',monospace;font-size:12px}
</style></head><body>__SIDEBAR__<div class="main">
<h1>Aleph for TAK</h1><div class="sub">Draw an area in ATAK or CloudTAK, get an offline data package of it — open-data imagery, DTED elevation, OSM features, street-level photos.</div>
__BANNER__
<div class="card"><div class="grid">
<div class="item"><div class="label">Public URL (give this to plugins)</div><div class="value">__URL__</div></div>
<div class="item"><div class="label">Service version</div><div class="value">__VERSION__</div></div>
<div class="item"><div class="label">Captures</div><div class="value">__JOBS__</div></div>
<div class="item"><div class="label">Console hook</div><div class="value">attached ✓ (infra-TAK __CONSOLE_VERSION__)</div></div>
</div></div>
<div class="card"><a class="btn" href="/aleph/admin" target="_blank" rel="noopener">Open Aleph admin ↗</a>
<div class="dim">Admin opens signed in as you (single sign-on from this console). Create ATAK client tokens there, pick the imagery source, and see every capture.<br>
Update or remove from the server shell: <code>sudo bash /opt/aleph-tak/src/infratak/install.sh</code> · <code>sudo bash /opt/aleph-tak/src/infratak/uninstall.sh</code></div></div>
</div></body></html>"""


def _register_routes(g):
    app, login_required = g["app"], g["login_required"]
    if "aleph_console_page" in app.view_functions:
        return
    from flask import redirect, session

    def page():
        installed, running, detail = _service_status()
        sidebar = ""
        try:
            if "render_sidebar" in g and "detect_modules" in g:
                sidebar = g["render_sidebar"](g["detect_modules"](), "aleph")
        except Exception as error:
            _log(f"sidebar unavailable on this page: {error!r}")
        if running:
            banner = '<div class="banner ok">● Running</div>'
        elif installed:
            banner = '<div class="banner bad">● Installed but not responding — <code>systemctl status aleph-tak</code></div>'
        else:
            banner = '<div class="banner bad">● Service not installed</div>'
        jobs = ", ".join(f"{count} {state}" for state, count in sorted((detail.get("jobs") or {}).items())) or "none yet"
        body = (PAGE.replace("__SIDEBAR__", sidebar).replace("__BANNER__", banner)
                .replace("__URL__", html.escape(_public_url() or "not set — deploy Caddy, then re-run install.sh"))
                .replace("__VERSION__", html.escape(str(detail.get("version", "—"))))
                .replace("__JOBS__", html.escape(jobs))
                .replace("__CONSOLE_VERSION__", html.escape(str(g.get("VERSION", "?")))))
        return body

    def admin_sso():
        # Mint a 60-second single-sign-on link for Aleph's /admin, signed with the key the
        # service generated (this console runs as root and can read it; nobody else can).
        import hashlib
        import hmac
        key = _read_json(os.path.join(DATA_DIR, "secrets.json")).get("console_sso_key")
        base = _public_url()
        if not key or not base:
            return "Aleph service is not installed or has no public URL yet.", 503
        user = str(session.get("authentik_username") or "admin")
        expires = int(time.time()) + 60
        signature = hmac.new(key.encode(), f"sso\n{user}\n{expires}".encode(), hashlib.sha256).hexdigest()
        from urllib.parse import urlencode
        return redirect(f"{base}/admin/sso?" + urlencode(dict(user=user, exp=expires, sig=signature)))

    app.add_url_rule("/aleph", "aleph_console_page", login_required(page))
    app.add_url_rule("/aleph/admin", "aleph_console_admin_sso", login_required(admin_sso))


def attach(module):
    g = module if isinstance(module, dict) else vars(module)
    attached = []
    steps = [
        ("routes", ("app", "login_required"), _register_routes),
        ("module card", ("detect_modules",), _wrap_detect_modules),
        ("sidebar", ("render_sidebar",), _wrap_render_sidebar),
        ("caddy", ("generate_caddyfile",), _wrap_generate_caddyfile),
    ]
    for name, needs, step in steps:
        if not all(key in g for key in needs):
            continue
        try:
            step(g)
            attached.append(name)
        except Exception as error:
            _log(f"{name} not attached: {error!r}")
    defaults = g.get("SERVICE_DOMAIN_DEFAULTS")
    if isinstance(defaults, dict):
        defaults.setdefault("aleph", "aleph")
        attached.append("domain")
    _log(f"attached to infra-TAK {g.get('VERSION', '?')}: {', '.join(attached) or 'nothing'}")
    return attached
