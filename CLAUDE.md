# CLAUDE.md — Aleph for TAK

Facts an agent needs that the code can't show. Workspace-wide rules: `../CLAUDE.md`.

## Shape of the repo
- One service (`service/`, Python) + three integrations: infra-TAK host (`infratak/`), CloudTAK
  plugin (`cloudtak/`), ATAK plugin (`atak/`). **`docs/API.md` is the contract** between them;
  change it together with `service/tests/test_api.py`, then the clients.
- `service/aleph_tak/core/` is a one-time fork of Aleph. Don't sync upstream (see core/FORK.md).
  Never reintroduce a Google endpoint — that's the plan's main blocker, not a style choice.

## Versioning
- Root `VERSION` is the single source: the service reads it, `atak/app/build.gradle` reads it,
  and `cloudtak/plugin/package.json` "version" must match it. Bump **PATCH only** (0.1.0 → 0.1.1)
  per build unless Jon asks otherwise.
- `API_VERSION` (service/aleph_tak/__init__.py) changes only on a breaking /api/v1 change; both
  clients hard-check it (`Models.SUPPORTED_API`, `SUPPORTED_API` in lib/client.ts).

## infra-TAK rules (load-bearing)
- **Never patch infra-TAK's `app.py` by default.** Update Now runs `git checkout --force` and
  erases it. Integration = runtime import hook (`infratak/aleph_infratak*.py`). New console
  features go in `attach()` and must be feature-detected (`if "x" in g`).
- After touching the hook, run `INFRATAK_REPO=… python -m unittest tests.test_infratak_hook`
  over all tags, including v10.x (`git fetch upstream --tags` first — a stale checkout hides
  new releases). docs/INFRATAK-COMPATIBILITY.md has the command. It must stay 100%.
- The Caddy block lives below `# --- User-added blocks (do not remove) ---`. Don't put it
  anywhere else; infra-TAK regenerates the rest of the file.

## Commands
- Service tests: `cd service && python -m unittest discover -s tests -t .`
- CloudTAK gate: `CLOUDTAK_DIR=<CloudTAK checkout with api/web npm-installed> node cloudtak/check-in-cloudtak.mjs`
- ATAK: `cd atak && JAVA_HOME="C:/Program Files/Android/Android Studio/jbr" ./gradlew assembleCivDebug testCivDebugUnitTest`
  (local.properties: forward slashes — see local.properties.example).
- Regenerate the Java DTED fixture after changing `formats/dted.py`: `cd service && python -m tests.make_atak_fixture`.

## Never run without Jon asking
- `infratak/install.sh` / `uninstall.sh` on any real host, or `cloudtak/install.sh` against a
  live CloudTAK (it rebuilds the API image). They're for servers, not dev boxes.
- Anything that pushes or tags.

## Gotchas
- Aleph's PBF reader uses multiprocessing **spawn**: any script that drives a capture needs an
  `if __name__ == "__main__":` guard (the service's `python -m aleph_tak` has one).
- USGS NAIP is an ImageServer (renders per request) and 502s under bursts; imagery uses 4
  workers and tolerates per-tile failures (`net.py`). Don't raise concurrency without testing live.
- DTED in packages is `ignore="true"` on purpose (see README deviations).
