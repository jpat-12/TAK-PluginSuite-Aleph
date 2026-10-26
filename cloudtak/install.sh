#!/usr/bin/env bash
#
# install.sh — put the Aleph CloudTAK plugin into a CloudTAK checkout and rebuild.
#
# Both halves are copied into place, because CloudTAK's WEB_PLUGINS clone can't carry a server
# route (and nests the web entry one level too deep for Vite's `plugins/*/index.ts` glob).
# Works with both CloudTAK source layouts (detected below):
#   plugin/                 → app/plugins/aleph/          (13.1xx+)  or api/web/plugins/aleph/ (older)
#   server/plugin-aleph.ts  → api/stateless/routes/       (13.1xx+)  or api/routes/            (older)
# The Aleph service URL and proxy token are merged into <CloudTAK>/api/.env — a JSON file
# CloudTAK loads at startup and git ignores, so no core file is edited and infra-TAK's
# CloudTAK updates (git pull --autostash) leave it alone.
#
# Usually run for you by `infratak/install.sh --cloudtak`, which creates the proxy token.
#
# Usage:
#   ALEPH_URL=https://aleph.example.org ALEPH_TOKEN=alt_… ./install.sh [/path/to/CloudTAK]   (default: found from the running cloudtak-api-1 container)
#   ./install.sh --remove [/path/to/CloudTAK]
#   add --no-build to copy/remove files without rebuilding the CloudTAK containers
#
# Requires: bash, python3, and (unless --no-build) docker compose.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="aleph"
ACTION="install"; DO_BUILD=1; CT_DIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --remove)   ACTION="remove" ;;
        --no-build) DO_BUILD=0 ;;
        -h|--help)  sed -n '/^# Usage:/,/^# Requires:/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)         echo "Unknown option: $1" >&2; exit 2 ;;
        *)          CT_DIR="$1" ;;
    esac
    shift
done
# Where CloudTAK runs from: the argument, else the running api container's compose dir, else ~/CloudTAK.
if [ -z "$CT_DIR" ] && command -v docker >/dev/null 2>&1; then
    CT_DIR="$(docker inspect cloudtak-api-1 --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true)"
fi
CT_DIR="${CT_DIR:-$HOME/CloudTAK}"

# CloudTAK has two source layouts; the plugin code is the same, only where it lands differs.
#   ≤ ~13.19:  api/web/plugins/<name>/   api/routes/            route imports ../lib/{auth,config}.js
#   13.1xx+ :  app/plugins/<name>/       api/stateless/routes/  route imports ../../common/auth.js, ../config.js
if [ -f "$CT_DIR/app/plugin.ts" ] && [ -d "$CT_DIR/api/stateless/routes" ]; then
    LAYOUT="split"
    WEB_DEST="$CT_DIR/app/plugins/$NAME"
    ROUTE_DEST="$CT_DIR/api/stateless/routes/plugin-aleph.ts"
elif [ -f "$CT_DIR/api/web/plugin.ts" ] && [ -d "$CT_DIR/api/routes" ]; then
    LAYOUT="legacy"
    WEB_DEST="$CT_DIR/api/web/plugins/$NAME"
    ROUTE_DEST="$CT_DIR/api/routes/plugin-aleph.ts"
else
    echo "ERROR: $CT_DIR doesn't look like a CloudTAK checkout (no app/plugin.ts or api/web/plugin.ts)." >&2
    exit 1
fi
ENV_FILE="$CT_DIR/api/.env"
CT_VERSION="$(python3 -c "import json;print(json.load(open('$CT_DIR/package.json')).get('version','?'))" 2>/dev/null || echo '?')"
echo "==> CloudTAK $CT_VERSION at $CT_DIR ($LAYOUT layout)"

# Merge (or drop) our two keys without disturbing anything else in api/.env.
edit_env() {
    python3 - "$ENV_FILE" "$1" <<'PYEOF'
import json, os, sys
path, action = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path)) if os.path.exists(path) else {}
except ValueError:
    sys.exit(f"{path} exists but isn't JSON; add ALEPH_URL/ALEPH_TOKEN to it by hand.")
if action == "set":
    data.update(ALEPH_URL=os.environ["ALEPH_URL"], ALEPH_TOKEN=os.environ["ALEPH_TOKEN"])
else:
    data.pop("ALEPH_URL", None); data.pop("ALEPH_TOKEN", None)
old = os.umask(0o077)
with open(path, "w") as stream:
    json.dump(data, stream, indent=4)
os.umask(old)
PYEOF
}

if [ "$ACTION" = "install" ]; then
    : "${ALEPH_URL:?set ALEPH_URL (e.g. https://aleph.example.org)}"
    : "${ALEPH_TOKEN:?set ALEPH_TOKEN (a proxy token: aleph-tak create-token cloudtak proxy)}"
    rm -rf "$WEB_DEST"
    mkdir -p "$WEB_DEST"
    cp -r "$HERE/plugin/index.ts" "$HERE/plugin/components" "$HERE/plugin/lib" "$WEB_DEST/"
    if [ "$LAYOUT" = "split" ]; then
        sed -e "s#from '../lib/auth.js'#from '../../common/auth.js'#"             -e "s#^import Config from '../lib/config.js';#import type Config from '../config.js';#"             "$HERE/server/plugin-aleph.ts" > "$ROUTE_DEST"
    else
        cp "$HERE/server/plugin-aleph.ts" "$ROUTE_DEST"
    fi
    edit_env set
    echo "==> Installed web half → $WEB_DEST, server half → $ROUTE_DEST, settings → $ENV_FILE"
else
    rm -rf "$CT_DIR/app/plugins/$NAME" "$CT_DIR/api/web/plugins/$NAME"            "$CT_DIR/api/stateless/routes/plugin-aleph.ts" "$CT_DIR/api/routes/plugin-aleph.ts"
    [ -f "$ENV_FILE" ] && edit_env remove
    echo "==> Removed the Aleph plugin from $CT_DIR"
fi

if [ "$DO_BUILD" -eq 1 ]; then
    # Same two steps infra-TAK's own CloudTAK plugin installer runs; --no-cache so the Vite
    # bundle can't come from a layer cached before the plugin files changed.
    echo "==> Rebuilding the CloudTAK API image (5–15 min; the build also lint/type-checks the plugin)"
    (cd "$CT_DIR" && docker compose build --no-cache api && docker compose up -d --force-recreate api)
    echo "==> Done. In the browser: CloudTAK → Settings → Refresh App (a hard refresh is not enough)."
fi
