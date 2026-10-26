"""The console hook against real infra-TAK app.py files, oldest release to current dev.

Needs an infra-TAK git checkout: set INFRATAK_REPO=/path/to/infra-TAK (skipped otherwise).
Each version's app.py is imported in its own subprocess from a throwaway directory (with a
stub start.sh, which is how the boot hook recognises infra-TAK), with the hook installed
exactly as the .pth file installs it in production.
"""

import io
import json
import os
import tarfile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INFRATAK = Path(__file__).resolve().parents[2] / "infratak"
REPO = os.environ.get("INFRATAK_REPO")
VERSIONS = os.environ.get("INFRATAK_VERSIONS", "v0.1.0-alpha v0.6.1-alpha v0.9.0-alpha upstream/dev").split()

PROBE = r"""
import json, os, subprocess, sys
sys.path.insert(0, sys.argv[1])
if os.name == "nt":
    # Old consoles (e.g. v0.1.5) call systemctl/docker unguarded inside detect_modules; on a
    # Windows dev box answer them as a Linux host with nothing installed would.
    _run = subprocess.run
    def run(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and args[0] in ("systemctl", "docker", "caddy", "ufw"):
            return subprocess.CompletedProcess(args, 3, "inactive\n", "")
        return _run(args, *a, **k)
    subprocess.run = run
    os.getuid = lambda: 0                      # v10+ checks for root at import (Linux-only API)
import aleph_infratak_boot           # what aleph_infratak.pth does at interpreter start
import aleph_infratak
aleph_infratak._service_status = lambda: (True, True, {"version": "test", "jobs": {"complete": 2}})
aleph_infratak._public_url = lambda: "https://aleph.example.org"
import app as console                # what gunicorn's `app:app` does
client = console.app.test_client()
with client.session_transaction() as s:
    s["authenticated"] = True
modules = console.detect_modules()
result = dict(
    version=getattr(console, "VERSION", "?"),
    routes=sorted(r.rule for r in console.app.url_map.iter_rules() if r.rule.startswith("/aleph")),
    card=modules.get("aleph", {}).get("route"),
    has_domains=hasattr(console, "SERVICE_DOMAIN_DEFAULTS"),
    domain=getattr(console, "SERVICE_DOMAIN_DEFAULTS", {}).get("aleph"),
)
page = client.get("/aleph")
result["page_status"] = page.status_code
result["page_has_url"] = b"https://aleph.example.org" in page.data
if hasattr(console, "render_sidebar"):
    nav = console.render_sidebar(modules, "aleph")
    result["sidebar_link"] = 'href="/aleph"' in nav
    ours = nav.find('href="/aleph"')
    after = [nav.find(a) for a in ('href="/connectivity"', 'href="/marketplace"', 'onclick="toggleTheme()"') if a in nav]
    result["sidebar_placed"] = not after or ours < min(after)
    link = nav[ours:nav.find("</a>", ours)]
    result["sidebar_no_font_icon"] = "material-symbols" not in link
anonymous = console.app.test_client().get("/aleph")
result["anonymous_status"] = anonymous.status_code
print("PROBE" + json.dumps(result), flush=True)
# Some console versions start non-daemon background threads at import (update checks, monitors);
# a normal exit would wait on them forever. We have our answer — leave immediately.
os._exit(0)
"""


@unittest.skipUnless(REPO, "set INFRATAK_REPO to an infra-TAK checkout to run")
class InfraTAKVersionTests(unittest.TestCase):
    def probe(self, ref):
        # The whole tree, not just app.py: from v10.1.22 the console imports its own modules/ package.
        tree = subprocess.run(["git", "-C", REPO, "archive", "--format=tar", ref], capture_output=True, check=True).stdout
        # ignore_cleanup_errors: on Windows a timed-out probe can briefly keep the folder locked.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            console = Path(tmp) / "infra-TAK"
            console.mkdir()
            with tarfile.open(fileobj=io.BytesIO(tree)) as archive:
                archive.extractall(console)
            (console / ".config").mkdir(exist_ok=True)
            if not (console / "start.sh").exists():
                (console / "start.sh").write_text("#!/bin/bash\n")
            env = {**os.environ, "CONFIG_DIR": str(console / ".config"), "PYTHONPATH": str(console),
                   "PYTHONIOENCODING": "utf-8"}  # v10 prints "→"; a Windows console codepage can't
            run = subprocess.run([sys.executable, "-c", PROBE, str(INFRATAK)], cwd=console, env=env,
                                 capture_output=True, text=True, timeout=180)
        line = next((l for l in run.stdout.splitlines() if l.startswith("PROBE")), None)
        self.assertIsNotNone(line, f"{ref} probe failed:\n{run.stdout[-1500:]}\n{run.stderr[-3000:]}")
        return json.loads(line[5:]), run.stderr

    def test_every_version_gets_the_full_integration(self):
        for ref in VERSIONS:
            with self.subTest(version=ref):
                result, log = self.probe(ref)
                self.assertIn("[aleph-tak] attached to infra-TAK", log)
                self.assertEqual(result["routes"], ["/aleph", "/aleph/admin"])
                self.assertEqual(result["card"], "/aleph")
                if result["has_domains"]:                    # added to infra-TAK in v0.2
                    self.assertEqual(result["domain"], "aleph")
                self.assertEqual(result["page_status"], 200)
                self.assertTrue(result["page_has_url"])
                self.assertIn(result["anonymous_status"], (302, 401))   # behind the console login
                if "sidebar_link" in result:
                    self.assertTrue(result["sidebar_link"])
                    self.assertTrue(result["sidebar_placed"], "Aleph must sit with the tools, above Connectivity/Marketplace")
                    self.assertTrue(result["sidebar_no_font_icon"], "icon must not depend on the console's icon-font subset")


if __name__ == "__main__":
    unittest.main()
