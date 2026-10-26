#!/bin/bash
# install.sh — install or update Aleph for TAK on an infra-TAK host (any infra-TAK version).
#
# Unlike the sibling InfraTAK-Module-* installers, this one never edits infra-TAK's app.py by
# default. infra-TAK's "Update Now" runs `git checkout --force <tag>`, which silently discards
# app.py patches, and the text anchors such patches need differ between releases. So:
#
#   1. The capture service runs on its own: /opt/aleph-tak, its own venv and system user, its
#      own systemd unit (aleph-tak.service, 127.0.0.1:8781). Works with or without a console.
#   2. Caddy gets an aleph.<fqdn> site block placed below infra-TAK's
#      "# --- User-added blocks (do not remove) ---" marker, which every regeneration since
#      v0.2.0 preserves. aleph-tak-heal.path re-adds it on v0.1.x (and after anything else).
#   3. The console integration (dashboard card, sidebar link, /aleph page, admin single
#      sign-on) is an import hook in the console's site-packages (aleph_infratak.pth) that
#      attaches at runtime to whatever hook points that infra-TAK version has. Verified
#      against every infra-TAK release tag from v0.1.0-alpha to the current dev branch.
#
# Usage:
#   sudo bash infratak/install.sh [options]          install, or update in place (idempotent)
#
# Options:
#   --domain HOST          public host for the service (default: aleph.<infra-TAK fqdn>, or the
#                          `aleph_domain` setting if present)
#   --console-hook MODE    pth (default) | append (guarded block in app.py; re-added by heal
#                          after updates) | none (service + Caddy only)
#   --cloudtak [DIR]       also install the CloudTAK plugin into DIR (default: wherever the running
#                          cloudtak-api-1 container was started from) and wire
#                          it to this service with a proxy token; rebuilds CloudTAK
#   --no-caddy             don't touch the Caddyfile (e.g. you proxy it yourself)
#   --no-restart           don't restart the infra-TAK console (hook loads on its next restart)
#   --pull                 git pull the source checkout first (/opt/aleph-tak/src)
#
# Re-run any time; it upgrades the service and re-applies every integration.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALEPH_HOME="${ALEPH_HOME:-/opt/aleph-tak}"
# shellcheck source=lib.sh
source "$SRC_DIR/infratak/lib.sh"

ORIGINAL_ARGS=("$@")
DOMAIN=""; HOOK_MODE="pth"; CLOUDTAK=""; DO_CADDY=1; DO_RESTART=1; DO_PULL=0
usage() { sed -n '/^# Usage:/,/^# Re-run/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
    case "$1" in
        --domain)       shift; DOMAIN="${1:-}" ;;
        --console-hook) shift; HOOK_MODE="${1:-}" ;;
        --cloudtak)     if [ -n "${2:-}" ] && [ "${2#--}" = "$2" ]; then CLOUDTAK="$2"; shift; else CLOUDTAK="auto"; fi ;;
        --no-caddy)     DO_CADDY=0 ;;
        --no-restart)   DO_RESTART=0 ;;
        --pull)         DO_PULL=1 ;;
        -h|--help)      usage; exit 0 ;;
        *)              echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done
case "$HOOK_MODE" in pth|append|none) ;; *) echo "--console-hook must be pth, append or none" >&2; exit 2 ;; esac
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root (sudo bash $0)" >&2; exit 1; }

# --- 0. Source checkout ---------------------------------------------------------------
# /opt/aleph-tak/src is the canonical copy updates come from. Installing from somewhere else
# (a fresh clone) copies that tree there first.
if [ "$DO_PULL" -eq 1 ]; then
    git -C "$ALEPH_HOME/src" pull --ff-only
    # Re-exec the freshly pulled installer, minus --pull (or it would loop).
    args=()
    for a in "${ORIGINAL_ARGS[@]}"; do [ "$a" != "--pull" ] && args+=("$a"); done
    exec bash "$ALEPH_HOME/src/infratak/install.sh" "${args[@]}"
fi
if [ "$SRC_DIR" != "$ALEPH_HOME/src" ]; then
    log "Copying source to $ALEPH_HOME/src"
    mkdir -p "$ALEPH_HOME"
    rm -rf "$ALEPH_HOME/src.new"
    cp -a "$SRC_DIR" "$ALEPH_HOME/src.new"
    rm -rf "$ALEPH_HOME/src"
    mv "$ALEPH_HOME/src.new" "$ALEPH_HOME/src"
fi
SRC="$ALEPH_HOME/src"
VERSION="$(tr -d '[:space:]' < "$SRC/VERSION")"
log "Aleph for TAK $VERSION"

# --- 1. Python ≥ 3.10 + venv ------------------------------------------------------------
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || { echo "ERROR: Python 3.10+ required (found $(python3 --version 2>&1)). Ubuntu 22.04+ ships it." >&2; exit 1; }
if ! python3 -c 'import ensurepip, venv' 2>/dev/null; then
    log "Installing python3-venv"
    if command -v apt-get >/dev/null; then
        apt-get install -y -qq python3-venv >/dev/null || apt-get install -y -qq "python3.$(python3 -c 'import sys;print(sys.version_info[1])')-venv" >/dev/null
    elif command -v dnf >/dev/null; then dnf install -y -q python3 >/dev/null; fi
fi

# --- 2. Service user, files, venv --------------------------------------------------------
id aleph-tak >/dev/null 2>&1 || useradd --system --home-dir "$ALEPH_HOME" --no-create-home --shell /usr/sbin/nologin aleph-tak
mkdir -p "$ALEPH_HOME/app" "$ALEPH_HOME/bin" "$ALEPH_HOME/data"
rm -rf "$ALEPH_HOME/app/aleph_tak"
cp -a "$SRC/service/aleph_tak" "$ALEPH_HOME/app/aleph_tak"
cp "$SRC/VERSION" "$ALEPH_HOME/app/VERSION"
find "$ALEPH_HOME/app" -name __pycache__ -prune -exec rm -rf {} +
for f in aleph_caddy.py aleph_infratak.py aleph_infratak_boot.py aleph_infratak.pth lib.sh heal.sh uninstall.sh; do
    install -m 0755 "$SRC/infratak/$f" "$ALEPH_HOME/bin/$f"
done
[ -x "$ALEPH_HOME/venv/bin/python" ] || { log "Creating venv"; python3 -m venv "$ALEPH_HOME/venv"; }
log "Installing Python dependencies"
"$ALEPH_HOME/venv/bin/pip" install -q --upgrade pip >/dev/null
"$ALEPH_HOME/venv/bin/pip" install -q -r "$SRC/service/requirements.txt"
chown -R aleph-tak:aleph-tak "$ALEPH_HOME/data"
chmod 750 "$ALEPH_HOME/data"

cat > /usr/local/bin/aleph-tak <<EOF
#!/bin/bash
# Admin CLI for the Aleph for TAK service (runs as the service user). See: aleph-tak help
exec runuser -u aleph-tak -- env ALEPH_DATA_DIR=$ALEPH_HOME/data PYTHONPATH=$ALEPH_HOME/app $ALEPH_HOME/venv/bin/python -m aleph_tak "\$@"
EOF
chmod 755 /usr/local/bin/aleph-tak

# --- 3. Service unit -----------------------------------------------------------------------
install -m 0644 "$SRC/infratak/systemd/aleph-tak.service" /etc/systemd/system/aleph-tak.service
systemctl daemon-reload
systemctl enable --quiet aleph-tak.service
systemctl restart aleph-tak.service
for _ in $(seq 1 20); do
    curl -fsS http://127.0.0.1:8781/healthz >/dev/null 2>&1 && break
    sleep 0.5
done
curl -fsS http://127.0.0.1:8781/healthz >/dev/null 2>&1 && log "Service is up on 127.0.0.1:8781" \
    || { warn "Service didn't answer; check: journalctl -u aleph-tak -n 50"; }

# --- 4. infra-TAK console integration ---------------------------------------------------
CONSOLE_DIR="$(find_console_dir || true)"
CONSOLE_PY=""
if [ -z "$CONSOLE_DIR" ]; then
    warn "No infra-TAK console found — running standalone (service + Caddy only)."
    HOOK_MODE="none"
else
    log "infra-TAK console: $CONSOLE_DIR ($(grep -m1 '^VERSION' "$CONSOLE_DIR/app.py" | cut -d'"' -f2 || echo unknown))"
fi
if [ "$HOOK_MODE" = "pth" ]; then
    if CONSOLE_PY="$(find_console_python)" && site="$(install_pth_hook "$CONSOLE_PY")"; then
        log "Console hook installed in $site"
        remove_append_hook "$CONSOLE_DIR"
    else
        warn "Couldn't locate the console's Python; falling back to --console-hook append."
        HOOK_MODE="append"
    fi
fi
if [ "$HOOK_MODE" = "append" ]; then
    install_append_hook "$CONSOLE_DIR" && log "Console hook block added to $CONSOLE_DIR/app.py"
fi
cat > "$ALEPH_HOME/bin/aleph.env" <<EOF
# Written by install.sh; read by heal.sh and uninstall.sh.
CONSOLE_DIR="$CONSOLE_DIR"
HOOK_MODE="$HOOK_MODE"
ALEPH_DOMAIN="$DOMAIN"
DO_CADDY="$DO_CADDY"
EOF

# --- 5. Caddy -------------------------------------------------------------------------------
if [ "$DO_CADDY" -eq 1 ]; then
    python3 "$ALEPH_HOME/bin/aleph_caddy.py" ensure --reload --console-dir "$CONSOLE_DIR" ${DOMAIN:+--domain "$DOMAIN"} \
        || warn "Caddy not updated (see above). The service still runs on 127.0.0.1:8781."
    chown aleph-tak:aleph-tak "$ALEPH_HOME/data/config.json" 2>/dev/null || true
fi
# Self-heal: only meaningful when infra-TAK owns the Caddyfile or app.py.
if [ -n "$CONSOLE_DIR" ] || [ "$DO_CADDY" -eq 1 ]; then
    sed "s#@CONSOLE_DIR@#${CONSOLE_DIR:-/nonexistent}#" "$SRC/infratak/systemd/aleph-tak-heal.path" > /etc/systemd/system/aleph-tak-heal.path
    install -m 0644 "$SRC/infratak/systemd/aleph-tak-heal.service" /etc/systemd/system/aleph-tak-heal.service
    systemctl daemon-reload
    systemctl enable --quiet --now aleph-tak-heal.path
fi
systemctl restart aleph-tak.service  # pick up a public_url written by aleph_caddy.py
PUBLIC_URL="$(python3 -c "import json;print(json.load(open('$ALEPH_HOME/data/config.json')).get('public_url',''))" 2>/dev/null || true)"

# --- 6. Admin access -------------------------------------------------------------------------
if [ "$HOOK_MODE" = "none" ] && ! grep -q admin_password_hash "$ALEPH_HOME/data/secrets.json" 2>/dev/null; then
    ADMIN_PASSWORD="$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
    echo "$ADMIN_PASSWORD" | /usr/local/bin/aleph-tak set-admin-password >/dev/null
fi

# --- 7. CloudTAK -------------------------------------------------------------------------------
if [ -n "$CLOUDTAK" ]; then
    TOKEN_FILE="$ALEPH_HOME/cloudtak-proxy.token"
    if [ ! -s "$TOKEN_FILE" ]; then
        (umask 077; /usr/local/bin/aleph-tak create-token cloudtak proxy > "$TOKEN_FILE")
    fi
    # Non-fatal: a CloudTAK problem must not skip the console restart and summary below.
    # "auto" lets cloudtak/install.sh find CloudTAK from its running container.
    CT_ARGS=()
    [ "$CLOUDTAK" != "auto" ] && CT_ARGS=("$CLOUDTAK")
    if ALEPH_URL="${PUBLIC_URL:-http://127.0.0.1:8781}" ALEPH_TOKEN="$(cat "$TOKEN_FILE")" \
        bash "$SRC/cloudtak/install.sh" "${CT_ARGS[@]}"; then
        CLOUDTAK_RESULT="installed"
    else
        CLOUDTAK_RESULT="FAILED (see above) — retry: bash $SRC/cloudtak/install.sh [CloudTAK dir]"
        warn "CloudTAK plugin not installed; everything else is."
    fi
fi

[ "$HOOK_MODE" != "none" ] && [ "$DO_RESTART" -eq 1 ] && restart_console

echo
echo "✓ Aleph for TAK $VERSION installed."
echo "  Service:      systemctl status aleph-tak   (logs: journalctl -u aleph-tak -f)"
echo "  Public URL:   ${PUBLIC_URL:-not set — deploy Caddy with a base FQDN, then re-run this script}"
if [ "$HOOK_MODE" != "none" ]; then
    echo "  Console:      infra-TAK → Aleph (sidebar or dashboard card) → Open Aleph admin"
else
    echo "  Admin:        ${PUBLIC_URL:-http://127.0.0.1:8781}/admin"
    [ -n "${ADMIN_PASSWORD:-}" ] && echo "  Admin password (shown once): $ADMIN_PASSWORD"
fi
echo "  ATAK token:   aleph-tak create-token <callsign>   (or from the admin page)"
[ -n "$CLOUDTAK" ] && echo "  CloudTAK:     ${CLOUDTAK_RESULT:-skipped}"
[ -z "$CLOUDTAK" ] && docker inspect cloudtak-api-1 >/dev/null 2>&1 && echo "  CloudTAK:     re-run with --cloudtak to install the CloudTAK plugin too"
exit 0
