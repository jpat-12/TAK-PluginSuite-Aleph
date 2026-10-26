# Running on any infra-TAK version

The requirement: one Aleph build that installs on whatever infra-TAK a host runs — old or new —
and keeps working after that host clicks **Update Now**.

## Why the sibling modules' approach doesn't meet it

`InfraTAK-Module-MigrateAuthentik` and `InfraTAK-Plugin-TAKRestreamerQRCodes` install by
text-patching infra-TAK's `app.py`. Two problems, both verified against the infra-TAK repo:

1. **Update Now erases the patches.** `/api/update/apply` runs `git checkout --force <tag>`,
   which discards every edit to tracked files. After an update the module silently vanishes until
   someone re-runs its installer.
2. **The anchors aren't stable.** MigrateAuthentik needs the line
   `print(f'[esri] Failed to register Esri CoT Bridge module: {_e}', flush=True)` — which exists
   in none of the 125 release tags. Restreamer QR needs `# === Main Entry Point …`, absent in
   older releases.

## What Aleph does instead

| Piece | Mechanism | Survives Update Now? | Versions |
|---|---|---|---|
| Capture service | Own systemd unit `aleph-tak`, own venv and user under `/opt/aleph-tak` | yes — infra-TAK never touches it | all (even without infra-TAK) |
| HTTPS site | `aleph.<fqdn>` block placed **below** `# --- User-added blocks (do not remove) ---`, which infra-TAK carries into every regenerated Caddyfile | yes | v0.2.0+ natively; v0.1.x via the heal unit |
| Console card, sidebar link, `/aleph` page, admin SSO | **Import hook**: `aleph_infratak.pth` + two modules in the console venv's site-packages. When gunicorn imports `app`, `attach()` adds routes and wraps `detect_modules`, `render_sidebar`, `generate_caddyfile` on the live module | yes — site-packages isn't in infra-TAK's git | all — every hook point is feature-detected |
| Self-heal | `aleph-tak-heal.path` watches `/etc/caddy/Caddyfile` and `<console>/app.py`; on change, re-applies anything missing (idempotent) | — | all |

Nothing infra-TAK tracks in git is modified in the default (`pth`) mode. `--console-hook append`
is a fallback for consoles whose interpreter can't be found; it adds a guarded block to `app.py`
that the heal unit restores after updates.

## Hook points and where they exist

`attach()` uses each only if present (`infratak/aleph_infratak.py`):

| Hook point | Used for | Present |
|---|---|---|
| `app`, `login_required` | `/aleph`, `/aleph/admin` behind the console login | v0.1.0 → v10.2.30 |
| `detect_modules` | dashboard card | v0.1.0 → v10.2.30 |
| `render_sidebar` | "Aleph" nav link | v0.2.0 → v10.2.30 (skipped on v0.1.x) |
| `generate_caddyfile` | re-add the site block on regeneration | v0.1.0 → v10.2.30 |
| `SERVICE_DOMAIN_DEFAULTS` | `aleph` → `aleph.<fqdn>` default | v0.2.0 → v10.2.30 (skipped on v0.1.x) |

## Verified

`service/tests/test_infratak_hook.py` loads each version's real `app.py` from a git checkout,
installs the hook exactly as the `.pth` does, imports the console the way gunicorn does, and
checks the routes, card, sidebar link, login gate and page render:

```bash
cd service
INFRATAK_REPO=/path/to/infra-TAK \
INFRATAK_VERSIONS="$(git -C /path/to/infra-TAK tag | grep '^v' | sort -V | tr '\n' ' ') upstream/dev" \
python -m unittest tests.test_infratak_hook
```

Last runs (2026-10-26): **every release passes** — all 125 `v0.1.0-alpha` … `v0.9.44-alpha`
tags plus `upstream/main`, `upstream/dev` and the `CAP_Command_Portal` branch, and all 125
`v10.0.1-alpha` … `v10.2.30-alpha` tags. The probe extracts each version's whole tree
(from v10.1.22 the console imports its own `modules/` package) and, on Windows, stubs the
Linux-only calls v10 makes at import (`os.getuid`, `systemctl`).

## What it can't promise

- A future infra-TAK that **renames** a hook point loses only that piece (e.g. the sidebar
  link); the service, Caddy site and the other pieces keep working. Re-run the version test
  against the new tag to see which.
- If a future release starts the console without `start.sh` beside `app.py`, the boot hook won't
  recognise it; `install.sh --console-hook append` covers that case.
- A rebuilt console venv drops the hook files; the heal unit reinstalls them, but the console
  only loads them on its next restart.
