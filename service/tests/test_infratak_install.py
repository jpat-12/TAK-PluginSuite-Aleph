"""Installer pieces that don't need root: Caddyfile editing and the app.py fallback hook."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

INFRATAK = Path(__file__).resolve().parents[2] / "infratak"
spec = importlib.util.spec_from_file_location("aleph_caddy", INFRATAK / "aleph_caddy.py")
aleph_caddy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aleph_caddy)

# On Windows, PATH's bash is often WSL's, which can't see C:/ paths; prefer Git Bash.
GIT_BASH = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "bash.exe"
BASH = str(GIT_BASH) if os.name == "nt" and GIT_BASH.exists() else shutil.which("bash")

INFRATAK_CADDYFILE = """{
    email admin@example.org
}

tak.example.org {
    reverse_proxy 127.0.0.1:9090
}
"""


def regenerate_like_infratak(existing):
    """infra-TAK's generate_caddyfile(): fresh text + everything below the user-blocks marker."""
    fresh = INFRATAK_CADDYFILE.replace("9090", "9091")
    if aleph_caddy.USER_BLOCKS_MARKER in existing:
        fresh = fresh.rstrip() + "\n\n" + existing[existing.index(aleph_caddy.USER_BLOCKS_MARKER):].rstrip()
    return fresh


class CaddyTests(unittest.TestCase):
    def test_block_goes_below_the_user_marker_and_survives_regeneration(self):
        text = aleph_caddy.ensure(INFRATAK_CADDYFILE, aleph_caddy.block("aleph.example.org", "127.0.0.1:8781"))
        self.assertLess(text.index(aleph_caddy.USER_BLOCKS_MARKER), text.index("aleph.example.org {"))
        regenerated = regenerate_like_infratak(text)
        self.assertIn("aleph.example.org {", regenerated)
        self.assertIn("9091", regenerated)

    def test_ensure_is_idempotent_and_replaces_a_changed_host(self):
        once = aleph_caddy.ensure(INFRATAK_CADDYFILE, aleph_caddy.block("aleph.example.org", "127.0.0.1:8781"))
        twice = aleph_caddy.ensure(once, aleph_caddy.block("aleph.example.org", "127.0.0.1:8781"))
        self.assertEqual(once, twice)
        moved = aleph_caddy.ensure(once, aleph_caddy.block("capture.example.org", "127.0.0.1:8781"))
        self.assertNotIn("aleph.example.org", moved)
        self.assertEqual(moved.count(aleph_caddy.BEGIN), 1)
        self.assertEqual(moved.count(aleph_caddy.USER_BLOCKS_MARKER), 1)

    def test_strip_leaves_other_user_blocks(self):
        text = INFRATAK_CADDYFILE + "\n" + aleph_caddy.USER_BLOCKS_MARKER + "\n\nhealth.example.org {\n    respond 200\n}\n"
        text = aleph_caddy.ensure(text, aleph_caddy.block("aleph.example.org", "127.0.0.1:8781"))
        stripped = aleph_caddy.strip(text)
        self.assertNotIn("aleph", stripped)
        self.assertIn("health.example.org", stripped)

    def test_host_follows_infratak_domain_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".config").mkdir()
            settings = Path(tmp) / ".config" / "settings.json"
            settings.write_text(json.dumps({"fqdn": "prod.ilwg.us"}))
            self.assertEqual(aleph_caddy.aleph_host(tmp, tmp), "aleph.prod.ilwg.us")
            settings.write_text(json.dumps({"fqdn": "prod.ilwg.us", "aleph_domain": "capture"}))
            self.assertEqual(aleph_caddy.aleph_host(tmp, tmp), "capture.prod.ilwg.us")
            self.assertEqual(aleph_caddy.aleph_host(tmp, tmp, "maps.other.org"), "maps.other.org")

    def test_cli_writes_file_and_sets_public_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            console, data = Path(tmp) / "console", Path(tmp) / "data"
            (console / ".config").mkdir(parents=True)
            data.mkdir()
            (console / ".config" / "settings.json").write_text(json.dumps({"fqdn": "example.org"}))
            caddyfile = Path(tmp) / "Caddyfile"
            caddyfile.write_text(INFRATAK_CADDYFILE)
            code = aleph_caddy.main(["ensure", "--caddyfile", str(caddyfile), "--console-dir", str(console),
                                     "--aleph-data", str(data)])
            self.assertEqual(code, 0)
            self.assertIn("aleph.example.org {", caddyfile.read_text())
            self.assertEqual(json.loads((data / "config.json").read_text())["public_url"], "https://aleph.example.org")
            aleph_caddy.main(["remove", "--caddyfile", str(caddyfile)])
            self.assertNotIn("aleph", caddyfile.read_text())


@unittest.skipUnless(BASH, "needs bash")
class AppendHookTests(unittest.TestCase):
    APP = 'VERSION = "0.9.0-alpha"\napp = object()\n\n' + "x = 1\n" * 50 + "\nif __name__ == '__main__':\n    app.run()\n"

    def run_lib(self, function, console):
        script = f'source "{INFRATAK.as_posix()}/lib.sh"; ALEPH_HOME=/opt/aleph-tak; {function} "{console}"'
        return subprocess.run([BASH, "-c", script], capture_output=True, text=True, timeout=60)

    def test_append_then_remove_round_trips_and_lands_before_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app.py"
            app.write_text(self.APP)
            console = Path(tmp).as_posix()
            for _ in range(2):  # second run must not duplicate the block
                result = self.run_lib("install_append_hook", console)
                self.assertEqual(result.returncode, 0, result.stderr)
            patched = app.read_text()
            self.assertEqual(patched.count("aleph-tak console hook ("), 1)
            self.assertLess(patched.index("import aleph_infratak"), patched.index("if __name__ == '__main__'"))
            compile(patched, "app.py", "exec")
            self.run_lib("remove_append_hook", console)
            self.assertEqual(app.read_text().strip(), self.APP.strip())


if __name__ == "__main__":
    unittest.main()
