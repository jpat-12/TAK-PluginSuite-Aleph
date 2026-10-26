#!/bin/bash
# uninstall.sh — remove Aleph for TAK from this host. Reverses install.sh exactly.
#
# Usage:
#   sudo bash /opt/aleph-tak/bin/uninstall.sh            keep captures/config in /opt/aleph-tak/data
#   sudo bash /opt/aleph-tak/bin/uninstall.sh --purge    delete everything, including captures
#   add --cloudtak [DIR] to also remove the CloudTAK plugin (rebuilds CloudTAK)
#
# Safe to run twice; every step no-ops if already undone.

set -uo pipefail
ALEPH_HOME="${ALEPH_HOME:-/opt/aleph-tak}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
# shellcheck disable=SC1091
[ -f "$ALEPH_HOME/bin/aleph.env" ] && source "$ALEPH_HOME/bin/aleph.env"

PURGE=0; CLOUDTAK=""
while [ $# -gt 0 ]; do
    case "$1" in
        --purge)    PURGE=1 ;;
        --cloudtak) if [ -n "${2:-}" ] && [ "${2#--}" = "$2" ]; then CLOUDTAK="$2"; shift; else CLOUDTAK="auto"; fi ;;
        *)          echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 1; }

# Heal first, or it would re-add what we remove below.
systemctl disable --now aleph-tak-heal.path 2>/dev/null
rm -f /etc/systemd/system/aleph-tak-heal.path /etc/systemd/system/aleph-tak-heal.service

[ -f "$ALEPH_HOME/bin/aleph_caddy.py" ] && python3 "$ALEPH_HOME/bin/aleph_caddy.py" remove --reload

if py="$(find_console_python)"; then remove_pth_hook "$py"; fi
CONSOLE_DIR="${CONSOLE_DIR:-$(find_console_dir || true)}"
[ -n "$CONSOLE_DIR" ] && remove_append_hook "$CONSOLE_DIR"

systemctl disable --now aleph-tak.service 2>/dev/null
rm -f /etc/systemd/system/aleph-tak.service /usr/local/bin/aleph-tak
systemctl daemon-reload

if [ -n "$CLOUDTAK" ] && [ -f "$ALEPH_HOME/src/cloudtak/install.sh" ]; then
    if [ "$CLOUDTAK" = auto ]; then bash "$ALEPH_HOME/src/cloudtak/install.sh" --remove; else bash "$ALEPH_HOME/src/cloudtak/install.sh" --remove "$CLOUDTAK"; fi
fi

if [ "$PURGE" -eq 1 ]; then
    rm -rf "$ALEPH_HOME"
    userdel aleph-tak 2>/dev/null
    log "Removed $ALEPH_HOME (including all captures)."
else
    rm -rf "$ALEPH_HOME/app" "$ALEPH_HOME/venv"
    log "Kept $ALEPH_HOME/data (captures, tokens, settings) and $ALEPH_HOME/src. Use --purge to delete them."
fi
[ -n "$CONSOLE_DIR" ] && restart_console
echo "✓ Aleph for TAK removed."
