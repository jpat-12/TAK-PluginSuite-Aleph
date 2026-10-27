"""Capture jobs: a JSON record per job on disk, a small worker pool, and an expiry janitor.

The job record is the one canonical copy of a capture's state; the API, the admin page and
every client poll read it, nothing caches it. Work files live beside it (jobs/<id>/work), so a
job interrupted by a restart resumes from what's already downloaded.

Layers fail independently: a missing Mapillary token or a Geofabrik outage shouldn't cost the
team their imagery. A job fails only when every requested layer failed.
"""

import json
import logging
import queue
import re
import secrets
import shutil
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

from . import __version__
from .area import to_geojson
from .core.common import Client, now, write_json
from .formats import datapackage
from .layers import Context, elevation, imagery, osm, photos

log = logging.getLogger("aleph-tak")

ID_RE = re.compile(r"^j[0-9a-f]{12}$")
MODULES = dict(imagery=imagery, elevation=elevation, osm=osm, photos=photos)
FINAL = ("complete", "failed", "cancelled")


class Cancelled(Exception):
    pass


def slug(text, fallback):
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", (text or "").strip()).strip("-")[:40]
    return text or fallback


class JobStore:
    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def dir(self, job_id):
        if not ID_RE.match(job_id or ""):
            raise KeyError(job_id)
        return self.root / job_id

    def create(self, owner, polygon, area_km2, layers, options, name, ttl_hours):
        job_id = "j" + secrets.token_hex(6)
        created = datetime.now(timezone.utc)
        stem = slug(name, f"aleph-{created:%Y%m%d}-{job_id[1:7]}")
        job = dict(
            id=job_id, owner=owner, name=name or stem, file_stem=stem, state="queued",
            created_at=created.isoformat(timespec="seconds"), updated_at=now(),
            expires_at=(created + timedelta(hours=ttl_hours)).isoformat(timespec="seconds"),
            area=to_geojson(polygon), area_km2=round(area_km2, 3), layers=layers, options=options,
            progress={layer: dict(state="queued", phase=None, done=0, total=None) for layer in layers},
            percent=0, warnings=[], error=None, package=None, results={}, service_version=__version__,
        )
        self.dir(job_id).mkdir(parents=True)
        self.save(job)
        return job

    def get(self, job_id):
        try:
            path = self.dir(job_id) / "job.json"
        except KeyError:
            return None
        with self.lock:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None

    def save(self, job):
        job["updated_at"] = now()
        with self.lock:
            write_json(self.dir(job["id"]) / "job.json", job)

    def list(self, owner=None):
        jobs = []
        for path in self.root.glob("j*/job.json"):
            job = self.get(path.parent.name)
            if job and (owner is None or job["owner"] == owner):
                jobs.append(job)
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    def delete(self, job_id):
        with self.lock:
            shutil.rmtree(self.dir(job_id), ignore_errors=True)


def overall_percent(job):
    fractions = []
    for state in job["progress"].values():
        if state["state"] in ("complete", "failed"):
            fractions.append(1.0)
        elif state["state"] == "running" and state.get("total"):
            fractions.append(min(1.0, state["done"] / state["total"]))
        else:
            fractions.append(0.0)
    return round(95 * sum(fractions) / max(1, len(fractions)), 1)


class Runner:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.queue = queue.Queue()
        self.cancelled = set()
        self.lock = threading.Lock()
        self.threads = []

    def start(self):
        for job in self.store.list():
            if job["state"] in ("queued", "running"):
                # Interrupted by a restart: requeue; downloaded tiles are reused on resume.
                job["state"] = "queued"
                self.store.save(job)
                self.queue.put(job["id"])
        for i in range(max(1, int(self.config["max_concurrent_jobs"]))):
            thread = threading.Thread(target=self._worker, name=f"aleph-job-{i}", daemon=True)
            thread.start()
            self.threads.append(thread)
        threading.Thread(target=self._janitor, name="aleph-janitor", daemon=True).start()

    def submit(self, job_id):
        self.queue.put(job_id)

    def cancel(self, job_id):
        with self.lock:
            self.cancelled.add(job_id)
        job = self.store.get(job_id)
        if job and job["state"] == "queued":
            job["state"] = "cancelled"
            self.store.save(job)

    def _check(self, job_id):
        def check():
            with self.lock:
                if job_id in self.cancelled:
                    raise Cancelled()
        return check

    def _worker(self):
        while True:
            job_id = self.queue.get()
            try:
                self.run(job_id)
            except Exception:  # never let one job kill the worker thread
                log.error("[aleph-tak] job %s crashed:\n%s", job_id, traceback.format_exc())
                job = self.store.get(job_id)
                if job and job["state"] not in FINAL:
                    job.update(state="failed", error="Internal error; see the service log.")
                    self.store.save(job)

    def run(self, job_id):
        job = self.store.get(job_id)
        if not job or job["state"] in FINAL:
            return
        check = self._check(job_id)
        job["state"] = "running"
        self.store.save(job)
        def request_log(method, address, attempt, error=None):
            # Successes stay quiet; every failed attempt is logged, so a slow capture shows *why*
            # (USGS 502s, timeouts) in `journalctl -u aleph-tak` instead of just crawling.
            if error is not None:
                host = address.split("/")[2] if "://" in address else address
                log.warning("[aleph-tak] job %s: %s attempt %d failed: %s", job_id, host, attempt + 1, error)

        client = Client(cancel=check, cache_dir=self.config.cache_dir, request_log=request_log)
        polygon = [(lat, lon) for lon, lat in job["area"]["coordinates"][0][:-1]]
        results = {}
        for layer in job["layers"]:
            state = job["progress"][layer]
            state.update(state="running", phase=None, done=0, total=None, error=None)
            self.store.save(job)
            last_save = [0.0]
            last_log = [time.monotonic()]
            log.info("[aleph-tak] job %s: %s started", job_id, layer)

            def progress(phase, done=0, total=None, unit=None, state=state, layer=layer):
                check()
                state.update(phase=phase, done=done, total=total)
                if time.monotonic() - last_log[0] > 30:  # a heartbeat for long layers
                    log.info("[aleph-tak] job %s: %s — %s %s/%s", job_id, layer, phase, done, total or "?")
                    last_log[0] = time.monotonic()
                if time.monotonic() - last_save[0] > 1:
                    job["percent"] = overall_percent(job)
                    self.store.save(job)
                    last_save[0] = time.monotonic()

            ctx = Context(job_dir=self.store.dir(job_id), name=job["file_stem"], polygon=polygon,
                          options=job["options"], settings=self.config.settings, client=client, progress=progress)
            try:
                result = MODULES[layer].run(ctx)
            except Cancelled:
                return self._finish_cancelled(job)
            except Exception as error:
                log.warning("[aleph-tak] job %s layer %s failed: %s", job_id, layer, error)
                log.debug(traceback.format_exc())
                state.update(state="failed", error=str(error) or type(error).__name__)
            else:
                log.info("[aleph-tak] job %s: %s complete %s", job_id, layer, result.stats)
                results[layer] = result
                state.update(state="complete", stats=result.stats)
                job["warnings"].extend(result.warnings)
                job["results"][layer] = result.web
            job["percent"] = overall_percent(job)
            self.store.save(job)

        if not results:
            errors = "; ".join(f"{k}: {v.get('error')}" for k, v in job["progress"].items())
            job.update(state="failed", error=f"Every layer failed — {errors}")
            self.store.save(job)
            return
        try:
            check()
            job["package"] = self._package(job, results)
        except Cancelled:
            return self._finish_cancelled(job)
        job.update(state="complete", percent=100, finished_at=now())
        self.store.save(job)
        log.info("[aleph-tak] job %s complete: %s (%.1f MB)", job_id, job["package"]["filename"], job["package"]["bytes"] / 1e6)

    def _finish_cancelled(self, job):
        job = {**job, "state": "cancelled"}
        self.store.save(job)
        with self.lock:
            self.cancelled.discard(job["id"])

    def _package(self, job, results):
        attribution = [r.attribution for r in results.values() if r.attribution]
        entries = [entry for r in results.values() for entry in r.entries]
        summary = {key: job[key] for key in ("id", "name", "created_at", "area", "area_km2", "layers", "options", "warnings")}
        summary.update(format="aleph-tak-package", version=1, service_version=__version__,
                       layers_detail={k: v for k, v in job["progress"].items()}, attribution=attribution)
        entries.append(datapackage.Entry("aleph.json", data=json.dumps(summary, indent=2), ignore=True))
        entries.append(datapackage.Entry("ATTRIBUTION.txt", ignore=True, data=(
            f"{job['name']} — captured {job['created_at']} by Aleph for TAK {__version__}\n\n"
            + "\n".join(attribution)
            + "\n\nCapture code derived from Aleph (c) 2026 Belluxx, MIT License.\n")))
        filename = f"{job['file_stem']}.zip"
        info = datapackage.build(self.store.dir(job["id"]) / filename, job["name"], entries)
        return dict(filename=filename, **info)

    def _janitor(self):
        # Captured search areas can reveal mission details (plan: expire after the mission).
        while True:
            cutoff = now()
            for job in self.store.list():
                if job["expires_at"] < cutoff and job["state"] != "running":
                    log.info("[aleph-tak] expiring job %s (%s)", job["id"], job["name"])
                    self.store.delete(job["id"])
            time.sleep(600)
