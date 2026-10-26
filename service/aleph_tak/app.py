"""HTTP API (/api/v1) — the contract in docs/API.md. Plugins only ever talk to this."""

import logging

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from . import API_VERSION, __version__, sources
from .area import LAYERS, area_km2, estimate, parse_area, parse_layers
from .auth import AuthError, Signer, Tokens, identify
from .config import Config
from .core.common import CachedClient
from .core.geo import extent, measure
from .jobs import JobStore, Runner
from .layers.imagery import tile_path
from .point import lookup

log = logging.getLogger("aleph-tak")

MAX_ACTIVE_JOBS_PER_USER = 3
BBOX_FACTOR = 4  # a thin diagonal polygon still makes elevation fetch its whole bounding box


def available_layers(settings):
    layers = ["elevation"]
    try:
        sources.imagery_source(settings)
        layers.insert(0, "imagery")
    except ValueError:
        pass
    if settings["osm"]["enabled"]:
        layers.append("osm")
    if settings["photos"]["mapillary_token"]:
        layers.append("photos")
    return [layer for layer in LAYERS if layer in layers]


def parse_options(body, settings):
    raw = body.get("options") or {}
    if not isinstance(raw, dict):
        raise ValueError("options must be an object.")
    imagery = settings["imagery"]
    zoom = raw.get("imagery_zoom", imagery["zoom"])
    max_zoom = min(imagery["max_zoom"], sources.imagery_source(settings)["max_zoom"]) if "imagery" in available_layers(settings) else 18
    if type(zoom) is not int or not 12 <= zoom <= max_zoom:
        raise ValueError(f"options.imagery_zoom: whole number 12–{max_zoom}.")
    formats = raw.get("imagery_formats", ["mbtiles"] + list(imagery["extra_formats"]))
    if not isinstance(formats, list) or not set(formats) <= {"mbtiles", "geotiff"}:
        raise ValueError("options.imagery_formats: any of mbtiles, geotiff.")
    level = raw.get("dted_level", settings["elevation"]["dted_level"])
    if level not in (1, 2):
        raise ValueError("options.dted_level: 1 or 2.")
    return dict(imagery_zoom=zoom, imagery_formats=sorted(set(formats) | {"mbtiles"}),
                elevation_zoom=int(settings["elevation"]["zoom"]), dted_level=level)


def parse_request(body, settings):
    if not isinstance(body, dict):
        raise ValueError("Send a JSON object.")
    polygon = parse_area(body.get("area"))
    size = area_km2(polygon)
    south, west, north, east = extent(polygon)
    bbox_km2 = measure([(south, west), (south, east), (north, east), (north, west)])[0] / 1e6
    if size > settings["max_area_km2"]:
        raise ValueError(f"Area is {size:.2f} km²; this server allows up to {settings['max_area_km2']} km² per capture.")
    if bbox_km2 > settings["max_area_km2"] * BBOX_FACTOR:
        raise ValueError("Area's bounding box is too large; split long, thin areas into several captures.")
    layers = parse_layers(body.get("layers"), available_layers(settings))
    return polygon, size, layers, parse_options(body, settings)


def create_app(data_dir=None, *, start_runner=True):
    config = Config(data_dir)
    tokens = Tokens(config.data_dir / "tokens.json")
    store = JobStore(config.jobs_dir)
    runner = Runner(config, store)
    signer = Signer(config.secrets["signing_key"])
    app = Flask(__name__)
    app.secret_key = config.secrets["session_key"]
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=2 << 20)
    app.extensions["aleph"] = dict(config=config, tokens=tokens, store=store, runner=runner, signer=signer)

    def base_url():
        return (config["public_url"] or request.url_root).rstrip("/")

    def caller():
        try:
            return identify(tokens, request.headers)
        except AuthError as error:
            abort(_json_error(str(error), error.status))

    def own_job(job_id, owner):
        job = store.get(job_id)
        if not job or job["owner"] != owner:
            abort(_json_error("No such job.", 404))
        return job

    def signed(job_id, kind):
        lifetime = float(config["signed_url_hours"]) * 3600
        return signer.query(f"{job_id}:{kind}", lifetime)

    def require_signature(job_id, kind):
        if not signer.verify(f"{job_id}:{kind}", request.args.get("exp"), request.args.get("sig")):
            abort(_json_error("Link expired or invalid; refresh the job to get a new one.", 403))

    def view(job):
        result = {k: v for k, v in job.items() if k not in ("file_stem",)}
        if job["state"] == "complete":
            base = f"{base_url()}/api/v1/jobs/{job['id']}"
            links = dict(package=f"{base}/package?{signed(job['id'], 'package')}",
                         area=f"{base}/layers/area?{signed(job['id'], 'layers')}")
            web = job.get("results", {})
            if "tiles" in web.get("imagery", {}):
                links["tiles"] = f"{base}/tiles/{{z}}/{{x}}/{{y}}?{signed(job['id'], 'tiles')}"
                links["tiles_info"] = web["imagery"]["tiles"]
            for layer in ("osm", "photos"):
                if web.get(layer, {}).get("geojson"):
                    links[layer] = f"{base}/layers/{layer}?{signed(job['id'], 'layers')}"
            if "photos" in web:
                links["photo_image"] = f"{base}/photos/{{id}}?{signed(job['id'], 'photos')}"
            result["links"] = links
        return result

    @app.errorhandler(ValueError)
    def bad_request(error):
        return _json_error(str(error), 400)

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return _json_error(error.description, error.code)
        return error

    @app.after_request
    def cors(response):
        # Browsers fetch tiles/GeoJSON straight from here with signed links (no cookies, no
        # credentials), so a wildcard origin grants nothing a signature doesn't already.
        if request.path.startswith("/api/v1/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Aleph-User, Range"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, X-Content-SHA256"
        return response

    @app.get("/healthz")
    def health():
        return jsonify(ok=True, version=__version__)

    @app.get("/api/v1/info")
    def info():
        settings = config.settings
        try:
            imagery = sources.imagery_source(settings)
            imagery = dict(name=imagery["name"], coverage=imagery["coverage"], max_zoom=imagery["max_zoom"])
        except ValueError:
            imagery = None
        return jsonify(
            service="aleph-tak", version=__version__, api=API_VERSION,
            layers=available_layers(settings), max_area_km2=settings["max_area_km2"],
            imagery=imagery, default_imagery_zoom=settings["imagery"]["zoom"],
            dted_level=settings["elevation"]["dted_level"], job_ttl_hours=settings["job_ttl_hours"],
            point_lookup=True,
        )

    @app.post("/api/v1/estimate")
    def estimate_route():
        caller()
        polygon, _, layers, options = _parse(request, config)
        return jsonify(estimate(polygon, layers, options, config.settings))

    @app.post("/api/v1/jobs")
    def create_job():
        owner, _ = caller()
        body = request.get_json(silent=True) or {}
        polygon, size, layers, options = _parse(request, config)
        active = [j for j in store.list(owner) if j["state"] in ("queued", "running")]
        if len(active) >= MAX_ACTIVE_JOBS_PER_USER:
            abort(_json_error(f"You already have {len(active)} captures in progress; wait for one to finish.", 429))
        name = body.get("name") if isinstance(body.get("name"), str) else None
        job = store.create(owner, polygon, size, layers, options, name, config["job_ttl_hours"])
        job["estimate"] = estimate(polygon, layers, options, config.settings)
        store.save(job)
        runner.submit(job["id"])
        log.info("[aleph-tak] job %s queued by %s: %.2f km², %s", job["id"], owner, size, ",".join(layers))
        return jsonify(view(job)), 201

    @app.get("/api/v1/jobs")
    def list_jobs():
        owner, _ = caller()
        return jsonify(jobs=[view(job) for job in store.list(owner)])

    @app.get("/api/v1/jobs/<job_id>")
    def get_job(job_id):
        owner, _ = caller()
        return jsonify(view(own_job(job_id, owner)))

    @app.delete("/api/v1/jobs/<job_id>")
    def delete_job(job_id):
        owner, _ = caller()
        job = own_job(job_id, owner)
        if job["state"] in ("queued", "running"):
            runner.cancel(job_id)
            return jsonify(id=job_id, state="cancelling")
        store.delete(job_id)
        return jsonify(id=job_id, state="deleted")

    @app.post("/api/v1/jobs/<job_id>/retry")
    def retry_job(job_id):
        # Re-runs every layer; already-downloaded tiles are reused, so this costs only the gaps.
        owner, _ = caller()
        job = own_job(job_id, owner)
        if job["state"] in ("queued", "running"):
            abort(_json_error("Capture is still in progress.", 409))
        job.update(state="queued", error=None, percent=0, package=None, warnings=[], results={})
        for layer in job["layers"]:
            job["progress"][layer] = dict(state="queued", phase=None, done=0, total=None)
        store.save(job)
        runner.submit(job_id)
        return jsonify(view(job))

    @app.get("/api/v1/jobs/<job_id>/package")
    def package(job_id):
        # Bearer for native clients (ATAK), signed link for browsers (CloudTAK download button).
        if request.headers.get("Authorization"):
            owner, _ = caller()
            job = own_job(job_id, owner)
        else:
            require_signature(job_id, "package")
            job = store.get(job_id) or abort(404)
        if job["state"] != "complete" or not job.get("package"):
            abort(_json_error("Package not ready.", 409))
        path = store.dir(job_id) / job["package"]["filename"]
        # conditional=True gives Range/If-Range support: ATAK resumes interrupted downloads.
        response = send_file(path, mimetype="application/zip", as_attachment=True,
                             download_name=job["package"]["filename"], conditional=True, etag=job["package"]["sha256"])
        response.headers["X-Content-SHA256"] = job["package"]["sha256"]
        return response

    @app.get("/api/v1/jobs/<job_id>/tiles/<int:z>/<int:x>/<int:y>")
    def tile(job_id, z, x, y):
        require_signature(job_id, "tiles")
        path = tile_path(store.dir(job_id) / "work" / "imagery" / "tiles", z, x, y)
        if path is None:
            return "", 204  # empty tile: MapLibre draws nothing and logs no error
        response = send_file(path, mimetype="image/jpeg" if path.suffix == ".jpg" else "image/png", max_age=3600)
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response

    @app.get("/api/v1/jobs/<job_id>/layers/<name>")
    def geojson_layer(job_id, name):
        require_signature(job_id, "layers")
        job = store.get(job_id) or abort(404)
        if name == "area":
            return jsonify(type="Feature", geometry=job["area"], properties=dict(name=job["name"], id=job_id))
        if name not in ("osm", "photos"):
            abort(404)
        path = store.dir(job_id) / "work" / name / f"{name}.geojson"
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="application/geo+json", max_age=3600)

    @app.get("/api/v1/jobs/<job_id>/photos/<photo_id>")
    def photo(job_id, photo_id):
        require_signature(job_id, "photos")
        if not photo_id.isdigit():
            abort(404)
        path = store.dir(job_id) / "work" / "photos" / f"{photo_id}.jpg"
        if not path.is_file():
            abort(404)
        return send_file(path, mimetype="image/jpeg", max_age=3600)

    @app.get("/api/v1/point")
    def point():
        caller()
        try:
            lat, lon = float(request.args["lat"]), float(request.args["lon"])
        except (KeyError, ValueError):
            raise ValueError("Pass lat and lon as numbers.")
        if not (-85 <= lat <= 85 and -180 <= lon <= 180):
            raise ValueError("lat must be within ±85 and lon within ±180.")
        client = CachedClient(cache_dir=config.cache_dir / "http")
        return jsonify(lookup(client, config.settings, lat, lon))

    from .admin import register as register_admin
    register_admin(app)

    if start_runner:
        runner.start()
    return app


def _parse(req, config):
    return parse_request(req.get_json(silent=True), config.settings)


def _json_error(message, status):
    response = jsonify(error=message)
    response.status_code = status
    return response

