"""One version across the repo: VERSION drives the service and the APK; the CloudTAK plugin's
package.json is the one hand-edited copy, so it's checked here."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class VersionTests(unittest.TestCase):
    def test_single_version_everywhere(self):
        version = (ROOT / "VERSION").read_text().strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        from aleph_tak import __version__
        self.assertEqual(__version__, version)
        self.assertEqual(json.loads((ROOT / "cloudtak/plugin/package.json").read_text())["version"], version)
        csproj = (ROOT / "wintak/AlephWinTak/AlephWinTak.csproj").read_text()
        self.assertIn("ReadAllText('$(MSBuildThisFileDirectory)..\..\VERSION')", csproj)
        gradle = (ROOT / "atak/app/build.gradle").read_text()
        self.assertTrue(re.search(r'PLUGIN_VERSION = new File\(rootDir, "\.\./VERSION"\)', gradle))

    def test_clients_speak_the_service_api_major(self):
        from aleph_tak import API_VERSION
        ts = (ROOT / "cloudtak/plugin/lib/client.ts").read_text()
        java = (ROOT / "atak/app/src/main/java/com/atakmap/android/aleph/api/Models.java").read_text()
        cs = (ROOT / "wintak/AlephWinTak/Core/Models.cs").read_text(encoding="utf-8")
        self.assertIn(f"SupportedApi = {API_VERSION};", cs)
        self.assertIn(f"SUPPORTED_API = {API_VERSION};", ts)
        self.assertIn(f"SUPPORTED_API = {API_VERSION};", java)


if __name__ == "__main__":
    unittest.main()
