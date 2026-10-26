"""/admin — tokens, settings, and every job. One server-rendered page, no JS framework.

Login: the infra-TAK console's "Open Aleph admin" button (single sign-on link signed with the
shared console_sso_key), or a local admin password for hosts without the console hook.
"""

import hmac
import json
import secrets
import time

from flask import current_app, redirect, render_template_string, request, session, url_for
from markupsafe import escape
from werkzeug.security import check_password_hash

from . import __version__
from .auth import sso_signature
from .config import EDITABLE

SSO_MAX_AGE_S = 120

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Aleph for TAK — admin</title>
<style>
:root{--bg:#080b14;--card:#161b26;--border:#1e2736;--text:#f1f5f9;--dim:#94a3b8;--accent:#06b6d4;--red:#ef4444;--green:#10b981}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin:16px 0}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:top}th{color:var(--dim);font-weight:600}
input,select{background:#0a0e1a;border:1px solid var(--border);border-radius:6px;color:var(--text);padding:7px 10px;font:inherit;width:100%}
label{display:block;font-size:12px;color:var(--dim);margin:10px 0 4px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 16px}
button{background:var(--accent);color:#001;border:0;border-radius:6px;padding:8px 14px;font-weight:600;cursor:pointer}button.danger{background:transparent;color:var(--red);border:1px solid var(--red);padding:4px 10px}
.dim{color:var(--dim)}.mono{font-family:ui-monospace,monospace;word-break:break-all}.flash{border-color:var(--green)}.err{border-color:var(--red)}
.state-complete{color:var(--green)}.state-failed{color:var(--red)}.state-running{color:var(--accent)}
</style></head><body><main>
<h1>Aleph for TAK</h1><div class="dim">Capture service v{{ version }} · API v1 · {{ jobs|length }} job(s){% if user %} · signed in as {{ user }} · <form method="post" action="{{ url_for('admin_logout') }}" style="display:inline"><input type="hidden" name="csrf" value="{{ csrf }}"><button class="danger">Sign out</button></form>{% endif %}</div>
{% if message %}<div class="card flash">{{ message|safe }}</div>{% endif %}
{% if error %}<div class="card err">{{ error }}</div>{% endif %}
{% if not user %}
<div class="card"><h2>Sign in</h2>
<p class="dim">Open this page from the infra-TAK console (Aleph card → "Open admin"), or use the local admin password set at install.</p>
{% if has_password %}<form method="post" action="{{ url_for('admin_login') }}"><label>Admin password</label><input type="password" name="password" autofocus><p><button>Sign in</button></p></form>
{% else %}<p class="dim">No local password is set. Run <span class="mono">sudo aleph-tak set-admin-password</span> on the server.</p>{% endif %}</div>
{% else %}
<div class="card"><h2>API tokens</h2>
<p class="dim"><b>client</b>: one person or device (ATAK) — paste it with the server URL into the plugin settings. <b>proxy</b>: a server that names its own users (the CloudTAK plugin; install.sh creates one).</p>
<table><tr><th>Name</th><th>Role</th><th>Created</th><th>Last used</th><th></th></tr>
{% for t in tokens %}<tr><td>{{ t.name }}</td><td>{{ t.role }}</td><td>{{ t.created_at[:16] }}</td><td>{{ (t.last_used_at or '—')[:10] }}</td>
<td>{% if t.revoked %}<span class="dim">revoked</span>{% else %}<form method="post" action="{{ url_for('admin_revoke', token_id=t.id) }}"><input type="hidden" name="csrf" value="{{ csrf }}"><button class="danger">Revoke</button></form>{% endif %}</td></tr>{% endfor %}</table>
<form method="post" action="{{ url_for('admin_create_token') }}" class="grid"><input type="hidden" name="csrf" value="{{ csrf }}">
<div><label>Name (callsign or device)</label><input name="name" required maxlength="100"></div>
<div><label>Role</label><select name="role"><option>client</option><option>proxy</option></select></div>
<div><label>&nbsp;</label><button>Create token</button></div></form></div>
<div class="card"><h2>Settings</h2><form method="post" action="{{ url_for('admin_settings') }}"><input type="hidden" name="csrf" value="{{ csrf }}">
<div class="grid">
<div><label>Public URL (how clients reach this service)</label><input name="public_url" value="{{ s.public_url }}" placeholder="https://aleph.example.org"></div>
<div><label>Max area per capture (km²)</label><input name="max_area_km2" type="number" step="0.5" min="0.5" value="{{ s.max_area_km2 }}"></div>
<div><label>Delete captures after (hours)</label><input name="job_ttl_hours" type="number" min="1" value="{{ s.job_ttl_hours }}"></div>
<div><label>Imagery source</label><select name="imagery.source">{% for key, src in imagery_sources.items() %}<option value="{{ key }}" {{ 'selected' if s.imagery.source == key }}>{{ src.name }}</option>{% endfor %}<option value="custom" {{ 'selected' if s.imagery.source == 'custom' }}>Custom (licensed) source</option></select></div>
<div><label>Default imagery zoom (17 ≈ 1 m, 18 ≈ 0.5 m)</label><input name="imagery.zoom" type="number" min="12" max="20" value="{{ s.imagery.zoom }}"></div>
<div><label>Also include lossless GeoTIFF (≈8× larger)</label><select name="imagery.geotiff"><option value="0">No</option><option value="1" {{ 'selected' if 'geotiff' in s.imagery.extra_formats }}>Yes</option></select></div>
<div><label>Custom imagery URL ({z}/{x}/{y} template or ArcGIS exportImage)</label><input name="imagery.custom.url" value="{{ s.imagery.custom.url }}"></div>
<div><label>Custom imagery kind</label><select name="imagery.custom.kind"><option value="xyz">XYZ tiles</option><option value="arcgis-export" {{ 'selected' if s.imagery.custom.kind == 'arcgis-export' }}>ArcGIS exportImage</option></select></div>
<div><label>Custom imagery attribution</label><input name="imagery.custom.attribution" value="{{ s.imagery.custom.attribution }}"></div>
<div><label>DTED level</label><select name="elevation.dted_level"><option value="2">2 (≈30 m posts)</option><option value="1" {{ 'selected' if s.elevation.dted_level == 1 }}>1 (≈90 m posts)</option></select></div>
<div><label>OSM features</label><select name="osm.enabled"><option value="1">On</option><option value="0" {{ 'selected' if not s.osm.enabled }}>Off</option></select></div>
<div><label>Mapillary client token (enables photos)</label><input name="photos.mapillary_token" value="{{ s.photos.mapillary_token }}" autocomplete="off"></div>
<div><label>Max photos per capture</label><input name="photos.limit" type="number" min="1" max="2000" value="{{ s.photos.limit }}"></div>
<div><label>Geocoder (Photon) URL</label><input name="geocoder_url" value="{{ s.geocoder_url }}"></div>
<div><label>Browser link lifetime (hours)</label><input name="signed_url_hours" type="number" min="1" max="168" value="{{ s.signed_url_hours }}"></div>
</div><p><button>Save settings</button></p></form></div>
<div class="card"><h2>All captures</h2><table><tr><th>Name</th><th>Owner</th><th>State</th><th>km²</th><th>Layers</th><th>Created</th><th>Expires</th><th></th></tr>
{% for j in jobs %}<tr><td>{{ j.name }}</td><td>{{ j.owner }}</td><td class="state-{{ j.state }}">{{ j.state }}{% if j.state == 'running' %} {{ j.percent }}%{% endif %}</td><td>{{ j.area_km2 }}</td><td>{{ j.layers|join(', ') }}</td><td>{{ j.created_at[:16] }}</td><td>{{ j.expires_at[:16] }}</td>
<td><form method="post" action="{{ url_for('admin_delete_job', job_id=j.id) }}"><input type="hidden" name="csrf" value="{{ csrf }}"><button class="danger">{{ 'Cancel' if j.state in ('queued','running') else 'Delete' }}</button></form></td></tr>{% endfor %}</table></div>
{% endif %}
</main></body></html>"""


def _ext():
    return current_app.extensions["aleph"]


def _csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def _require_admin():
    if not session.get("admin_user"):
        return redirect(url_for("admin_page"))
    expected = session.get("csrf")
    # No token issued yet must fail too — otherwise an empty field matches an empty session.
    if not expected or not hmac.compare_digest(request.form.get("csrf", ""), expected):
        session["admin_error"] = "Form expired; try again."
        return redirect(url_for("admin_page"))
    return None


def _coerce(form):
    """Flat dotted form fields → the nested settings shape, with types restored."""
    current = _ext()["config"].settings
    values = {}

    def put(path, value):
        node = values
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value

    for field, raw in form.items():
        if field in ("csrf", "imagery.geotiff"):
            continue
        path = field.split(".")
        if path[0] not in EDITABLE:
            continue
        node = current
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, bool):
            value = raw == "1"
        elif isinstance(node, int):
            value = int(raw)
        elif isinstance(node, float):
            value = float(raw)
        else:
            value = raw.strip()
        put(path, value)
    values.setdefault("imagery", {})["extra_formats"] = ["geotiff"] if form.get("imagery.geotiff") == "1" else []
    if values.get("public_url"):
        values["public_url"] = values["public_url"].rstrip("/")
    return values


def register(app):
    @app.get("/admin")
    def admin_page():
        ext = _ext()
        from .sources import IMAGERY
        return render_template_string(
            PAGE, version=__version__, user=session.get("admin_user"), csrf=_csrf(),
            has_password=bool(ext["config"].secrets.get("admin_password_hash")),
            tokens=ext["tokens"].public(), jobs=ext["store"].list(), s=ext["config"].settings,
            imagery_sources=IMAGERY, message=session.pop("admin_message", None), error=session.pop("admin_error", None))

    @app.post("/admin/login")
    def admin_login():
        stored = _ext()["config"].secrets.get("admin_password_hash")
        if stored and check_password_hash(stored, request.form.get("password", "")):
            session.clear()
            session["admin_user"] = "admin"
        else:
            time.sleep(1)  # blunt brute force without lockout state
            session["admin_error"] = "Wrong password."
        return redirect(url_for("admin_page"))

    @app.get("/admin/sso")
    def admin_sso():
        key = _ext()["config"].secrets["console_sso_key"]
        user, expires, signature = request.args.get("user", ""), request.args.get("exp", "0"), request.args.get("sig", "")
        try:
            expires = int(expires)
        except ValueError:
            expires = 0
        fresh = time.time() <= expires <= time.time() + SSO_MAX_AGE_S
        if fresh and user and hmac.compare_digest(sso_signature(key, user, expires), signature):
            session.clear()
            session["admin_user"] = f"{user} (infra-TAK)"
        else:
            session["admin_error"] = "That sign-in link expired. Open admin again from the infra-TAK console."
        return redirect(url_for("admin_page"))

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_page"))

    @app.post("/admin/tokens")
    def admin_create_token():
        if (denied := _require_admin()):
            return denied
        try:
            token = _ext()["tokens"].create(request.form.get("name"), request.form.get("role", "client"))
            public_url = _ext()["config"]["public_url"] or request.url_root.rstrip("/")
            session["admin_message"] = (
                "Token created — copy it now, it won't be shown again:<br>"
                f"<p class='mono'>{token}</p><span class='dim'>Server URL for the plugin: "
                f"<span class='mono'>{escape(public_url)}</span></span>")
        except ValueError as error:
            session["admin_error"] = str(error)
        return redirect(url_for("admin_page"))

    @app.post("/admin/tokens/<token_id>/revoke")
    def admin_revoke(token_id):
        if (denied := _require_admin()):
            return denied
        _ext()["tokens"].revoke(token_id)
        session["admin_message"] = "Token revoked."
        return redirect(url_for("admin_page"))

    @app.post("/admin/settings")
    def admin_settings():
        if (denied := _require_admin()):
            return denied
        try:
            _ext()["config"].update(_coerce(request.form))
            session["admin_message"] = "Settings saved. They apply to captures started from now on."
        except (ValueError, TypeError) as error:
            session["admin_error"] = f"Settings not saved: {error}"
        return redirect(url_for("admin_page"))

    @app.post("/admin/jobs/<job_id>/delete")
    def admin_delete_job(job_id):
        if (denied := _require_admin()):
            return denied
        ext = _ext()
        job = ext["store"].get(job_id)
        if job and job["state"] in ("queued", "running"):
            ext["runner"].cancel(job_id)
        elif job:
            ext["store"].delete(job_id)
        return redirect(url_for("admin_page"))

    @app.get("/admin/api/status")
    def admin_status():
        """Read by the infra-TAK console card. Caddy also connects from loopback, but it always
        adds X-Forwarded-For — so a request without it came from this host directly."""
        if request.remote_addr not in ("127.0.0.1", "::1") or "X-Forwarded-For" in request.headers:
            return {"error": "loopback only"}, 403
        jobs = _ext()["store"].list()
        counts = {}
        for job in jobs:
            counts[job["state"]] = counts.get(job["state"], 0) + 1
        return json.dumps(dict(version=__version__, jobs=counts)), 200, {"Content-Type": "application/json"}
