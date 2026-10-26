"""The /api/v1 contract (docs/API.md) as clients see it, with capture layers stubbed."""

import tempfile
import time
import unittest
import zipfile
from io import BytesIO
from unittest import mock

from aleph_tak import jobs
from aleph_tak.app import create_app
from aleph_tak.auth import Signer, sso_signature
from aleph_tak.formats.datapackage import Entry
from aleph_tak.layers import LayerResult

AREA = {"type": "Polygon", "coordinates": [[[-89.655, 39.795], [-89.645, 39.795], [-89.645, 39.805],
                                            [-89.655, 39.805], [-89.655, 39.795]]]}


class FakeLayer:
    def __init__(self, name, fail=False):
        self.name, self.fail = name, fail

    def run(self, ctx):
        ctx.progress("working", 1, 2)
        if self.fail:
            raise OSError(f"{self.name} source down")
        out = ctx.output() / f"{self.name}.bin"
        out.write_bytes(self.name.encode() * 1000)
        if self.name == "imagery":
            tiles = ctx.work("imagery") / "tiles" / "16" / "1"
            tiles.mkdir(parents=True)
            (tiles / "2.jpg").write_bytes(b"\xff\xd8jpeg")
        return LayerResult(entries=[Entry(f"{self.name}/{self.name}.bin", out)], attribution=f"{self.name} credit",
                           stats={"ok": True}, web={"tiles": {"min_zoom": 10, "max_zoom": 16}} if self.name == "imagery" else {})


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(self.tmp.name, start_runner=False)
        self.ext = self.app.extensions["aleph"]
        self.client = self.app.test_client()
        self.token = self.ext["tokens"].create("CAP-IL-001")
        self.auth = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, layers=("imagery", "elevation"), headers=None):
        response = self.client.post("/api/v1/jobs", json={"area": AREA, "layers": list(layers), "name": "Lake search"},
                                    headers=headers or self.auth)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json

    def run_job(self, job_id, modules):
        with mock.patch.dict(jobs.MODULES, modules):
            self.ext["runner"].run(job_id)
        return self.client.get(f"/api/v1/jobs/{job_id}", headers=self.auth).json

    def test_info_is_public_and_versioned(self):
        info = self.client.get("/api/v1/info").json
        self.assertEqual(info["api"], 1)
        self.assertEqual(info["layers"], ["imagery", "elevation", "osm"])  # no Mapillary token → no photos
        self.assertEqual(info["imagery"]["coverage"], "Contiguous United States")

    def test_requests_need_a_valid_token(self):
        self.assertEqual(self.client.get("/api/v1/jobs").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/jobs", headers={"Authorization": "Bearer alt_000000000000_" + "x" * 43}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/jobs", headers=self.auth).status_code, 200)

    def test_estimate_and_area_cap(self):
        estimate = self.client.post("/api/v1/estimate", json={"area": AREA, "layers": ["imagery", "elevation"]},
                                    headers=self.auth).json
        self.assertTrue(estimate["allowed"])
        self.assertGreater(estimate["layers"]["imagery"]["tiles"], 0)
        self.assertEqual(estimate["layers"]["elevation"]["dted_cells"], 1)
        big = {"type": "Polygon", "coordinates": [[[-90, 39], [-89, 39], [-89, 40], [-90, 40], [-90, 39]]]}
        response = self.client.post("/api/v1/jobs", json={"area": big}, headers=self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertIn("km²", response.json["error"])

    def test_unavailable_layer_is_rejected(self):
        response = self.client.post("/api/v1/jobs", json={"area": AREA, "layers": ["photos"]}, headers=self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertIn("not available", response.json["error"])

    def test_job_runs_to_a_package_with_signed_links(self):
        job = self.submit()
        self.assertEqual(job["state"], "queued")
        done = self.run_job(job["id"], {"imagery": FakeLayer("imagery"), "elevation": FakeLayer("elevation")})
        self.assertEqual(done["state"], "complete")
        self.assertEqual(done["percent"], 100)
        links = done["links"]
        package = self.client.get(links["package"].replace("http://localhost", ""))
        self.assertEqual(package.status_code, 200)
        with zipfile.ZipFile(BytesIO(package.data)) as archive:
            names = set(archive.namelist())
            attribution = archive.read("ATTRIBUTION.txt").decode()
        self.assertTrue({"MANIFEST/manifest.xml", "imagery/imagery.bin", "elevation/elevation.bin", "aleph.json"} <= names)
        self.assertIn("imagery credit", attribution)
        self.assertIn("Belluxx", attribution)
        tile = self.client.get(links["tiles"].replace("http://localhost", "").replace("{z}/{x}/{y}", "16/1/2"))
        self.assertEqual((tile.status_code, tile.data), (200, b"\xff\xd8jpeg"))
        empty = self.client.get(links["tiles"].replace("http://localhost", "").replace("{z}/{x}/{y}", "16/9/9"))
        self.assertEqual(empty.status_code, 204)
        self.assertEqual(tile.headers["Access-Control-Allow-Origin"], "*")

    def test_package_download_resumes_with_range(self):
        job = self.submit()
        done = self.run_job(job["id"], {"imagery": FakeLayer("imagery"), "elevation": FakeLayer("elevation")})
        url = f"/api/v1/jobs/{job['id']}/package"
        whole = self.client.get(url, headers=self.auth)
        tail = self.client.get(url, headers={**self.auth, "Range": "bytes=100-"})
        self.assertEqual(tail.status_code, 206)
        self.assertEqual(tail.data, whole.data[100:])
        self.assertEqual(whole.headers["X-Content-SHA256"], done["package"]["sha256"])

    def test_one_failed_layer_is_a_warning_not_a_failure(self):
        job = self.submit()
        done = self.run_job(job["id"], {"imagery": FakeLayer("imagery"), "elevation": FakeLayer("elevation", fail=True)})
        self.assertEqual(done["state"], "complete")
        self.assertEqual(done["progress"]["elevation"]["state"], "failed")
        self.assertIn("source down", done["progress"]["elevation"]["error"])

    def test_all_layers_failing_fails_the_job(self):
        job = self.submit()
        done = self.run_job(job["id"], {"imagery": FakeLayer("imagery", True), "elevation": FakeLayer("elevation", True)})
        self.assertEqual(done["state"], "failed")
        self.assertNotIn("links", done)

    def test_signed_links_expire_and_are_scoped(self):
        job = self.submit()
        self.run_job(job["id"], {"imagery": FakeLayer("imagery"), "elevation": FakeLayer("elevation")})
        signer = Signer(self.ext["config"].secrets["signing_key"])
        expired = int(time.time()) - 1
        self.assertFalse(signer.verify(f"{job['id']}:package", expired, signer._mac(f"{job['id']}:package", expired)))
        tiles_sig = signer.query(f"{job['id']}:tiles", 60)
        response = self.client.get(f"/api/v1/jobs/{job['id']}/package?{tiles_sig}")
        self.assertEqual(response.status_code, 403)  # a tiles signature can't fetch the package

    def test_users_only_see_their_own_jobs(self):
        job = self.submit()
        other = {"Authorization": f"Bearer {self.ext['tokens'].create('someone-else')}"}
        self.assertEqual(self.client.get(f"/api/v1/jobs/{job['id']}", headers=other).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/jobs", headers=other).json["jobs"], [])

    def test_proxy_tokens_scope_jobs_per_named_user(self):
        proxy = self.ext["tokens"].create("cloudtak", "proxy")
        alice = {"Authorization": f"Bearer {proxy}", "X-Aleph-User": "alice@example.org"}
        bob = {"Authorization": f"Bearer {proxy}", "X-Aleph-User": "bob@example.org"}
        job = self.submit(headers=alice)
        self.assertEqual(job["owner"], "cloudtak:alice@example.org")
        self.assertEqual(self.client.get("/api/v1/jobs", headers=bob).json["jobs"], [])
        self.assertEqual(self.client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {proxy}"}).status_code, 400)

    def test_cancel_queued_job(self):
        job = self.submit()
        response = self.client.delete(f"/api/v1/jobs/{job['id']}", headers=self.auth)
        self.assertEqual(response.json["state"], "cancelling")
        self.assertEqual(self.client.get(f"/api/v1/jobs/{job['id']}", headers=self.auth).json["state"], "cancelled")

    def test_per_user_active_job_limit(self):
        for _ in range(3):
            self.submit()
        response = self.client.post("/api/v1/jobs", json={"area": AREA, "layers": ["imagery"]}, headers=self.auth)
        self.assertEqual(response.status_code, 429)

    def test_admin_sso_link_from_console(self):
        key = self.ext["config"].secrets["console_sso_key"]
        expires = int(time.time()) + 60
        good = self.client.get(f"/admin/sso?user=admin&exp={expires}&sig={sso_signature(key, 'admin', expires)}")
        self.assertEqual(good.status_code, 302)
        page = self.client.get("/admin").data.decode()
        self.assertIn("signed in as admin (infra-TAK)", page)

    def test_admin_forms_need_csrf(self):
        key = self.ext["config"].secrets["console_sso_key"]
        expires = int(time.time()) + 60
        self.client.get(f"/admin/sso?user=admin&exp={expires}&sig={sso_signature(key, 'admin', expires)}")
        before = len(self.ext["tokens"].items)
        self.client.post("/admin/tokens", data={"name": "x", "role": "client"})
        self.assertEqual(len(self.ext["tokens"].items), before)
        self.client.get("/admin")  # rendering the page issues the token, as in a browser
        with self.client.session_transaction() as session:
            csrf = session["csrf"]
        self.client.post("/admin/tokens", data={"name": "x", "role": "client", "csrf": csrf})
        self.assertEqual(len(self.ext["tokens"].items), before + 1)


if __name__ == "__main__":
    unittest.main()
