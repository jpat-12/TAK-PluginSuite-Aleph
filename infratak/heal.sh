#!/bin/bash
# heal.sh — run by aleph-tak-heal.service whenever infra-TAK rewrites its Caddyfile or app.py.
# Idempotent: if nothing is missing it changes nothing (so its own Caddyfile write, which
# re-triggers the path unit, ends in a no-op instead of a loop).
set -uo pipefail
ALEPH_HOME="${ALEPH_HOME:-/opt/aleph-tak}"
# shellcheck source=lib.sh
source "$ALEPH_HOME/bin/lib.sh"
# shellcheck disable=SC1091
[ -f "$ALEPH_HOME/bin/aleph.env" ] && source "$ALEPH_HOME/bin/aleph.env"

python3 "$ALEPH_HOME/bin/aleph_caddy.py" ensure --reload --console-dir "${CONSOLE_DIR:-}" \
    ${ALEPH_DOMAIN:+--domain "$ALEPH_DOMAIN"} || warn "Caddy block not re-applied"

case "${HOOK_MODE:-none}" in
    pth)
        # A rebuilt console venv loses site-packages files; put the hook back.
        if py="$(find_console_python)" && ! "$py" -c 'import aleph_infratak_boot' 2>/dev/null; then
            install_pth_hook "$py" >/dev/null && log "Console hook re-installed (takes effect on next console restart)"
        fi ;;
    append)
        if [ -n "${CONSOLE_DIR:-}" ] && ! grep -qF "$HOOK_BEGIN" "$CONSOLE_DIR/app.py"; then
            install_append_hook "$CONSOLE_DIR" && log "Console hook re-added to app.py (takes effect on next console restart)"
        fi ;;
esac
exit 0
