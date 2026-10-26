#!/bin/bash
# lib.sh — functions shared by install.sh, heal.sh and uninstall.sh. Sourced, never run.

ALEPH_HOME="${ALEPH_HOME:-/opt/aleph-tak}"
CONSOLE_SERVICE="${CONSOLE_SERVICE:-takwerx-console}"
HOOK_BEGIN="# >>> aleph-tak console hook"
HOOK_END="# <<< aleph-tak console hook"

log()  { echo "==> $*"; }
warn() { echo "    ⚠ $*" >&2; }

# Same search order as the sibling InfraTAK-Module-* installers.
find_console_dir() {
    local d
    for d in /opt/infra-TAK /opt/infra-tak /root/infra-TAK /root/infra-tak "$HOME/infra-TAK" "$HOME/infra-tak"; do
        [ -f "$d/app.py" ] && { echo "$d"; return 0; }
    done
    d="$(find /root /home /opt -maxdepth 3 -name app.py -path '*infra*' 2>/dev/null | head -1)"
    [ -n "$d" ] && dirname "$d"
}

# The interpreter that runs the console. Every infra-TAK release starts it either as
# `<venv>/bin/gunicorn ... app:app` or (pre-gunicorn) `<python> app.py`.
find_console_python() {
    local exec_start bin py
    exec_start="$(systemctl show -p ExecStart --value "$CONSOLE_SERVICE" 2>/dev/null | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)"
    if [ -z "$exec_start" ] && [ -f "/etc/systemd/system/$CONSOLE_SERVICE.service" ]; then
        exec_start="$(sed -n 's/^ExecStart=\([^ ]*\).*/\1/p' "/etc/systemd/system/$CONSOLE_SERVICE.service" | head -1)"
    fi
    bin="$exec_start"
    case "$(basename "${bin:-x}")" in
        gunicorn*) for py in "$(dirname "$bin")/python3" "$(dirname "$bin")/python"; do
                       [ -x "$py" ] && { echo "$py"; return 0; }
                   done ;;
        python*)   [ -x "$bin" ] && { echo "$bin"; return 0; } ;;
    esac
    return 1
}

console_site_packages() {
    "$1" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'
}

# Default hook: two modules + a .pth line in the console's site-packages. Untracked by
# infra-TAK's git, so "Update Now" (git checkout --force) leaves it alone.
install_pth_hook() {
    local py="$1" site
    site="$(console_site_packages "$py")" || return 1
    mkdir -p "$site"
    install -m 0644 "$ALEPH_HOME/bin/aleph_infratak.py" "$ALEPH_HOME/bin/aleph_infratak_boot.py" "$site/"
    install -m 0644 "$ALEPH_HOME/bin/aleph_infratak.pth" "$site/aleph_infratak.pth"
    "$py" -c 'import aleph_infratak_boot, aleph_infratak' || return 1
    echo "$site"
}

remove_pth_hook() {
    local py="$1" site
    site="$(console_site_packages "$py" 2>/dev/null)" || return 0
    rm -f "$site/aleph_infratak.pth" "$site/aleph_infratak.py" "$site/aleph_infratak_boot.py"
}

# Fallback hook for consoles that don't run from a findable interpreter: a guarded block in
# app.py itself. "Update Now" wipes it; aleph-tak-heal puts it back.
install_append_hook() {
    local app="$1/app.py"
    grep -qF "$HOOK_BEGIN" "$app" && return 0
    python3 - "$app" "$ALEPH_HOME/bin" "$HOOK_BEGIN" "$HOOK_END" <<'PYEOF'
import re, sys
path, bindir, begin, end = sys.argv[1:]
src = open(path, encoding="utf-8").read()
block = (f"{begin} (re-added by aleph-tak-heal after infra-TAK updates)\n"
         "try:\n"
         f"    import sys as _aleph_sys; _aleph_sys.path.insert(0, {bindir!r})\n"
         "    import aleph_infratak as _aleph; _aleph.attach(globals())\n"
         "except Exception as _aleph_error:\n"
         "    print(f'[aleph-tak] console hook skipped: {_aleph_error!r}', flush=True)\n"
         f"{end}\n")
# Before the direct-run entry point if there is one (it blocks in app.run), else at the end.
match = list(re.finditer(r"^if __name__ == ['\"]__main__['\"]:", src, re.M))
if match and match[-1].start() > len(src) // 2:
    src = src[:match[-1].start()] + block + "\n" + src[match[-1].start():]
else:
    src = src.rstrip("\n") + "\n\n" + block
open(path, "w", encoding="utf-8").write(src)
PYEOF
}

remove_append_hook() {
    local app="$1/app.py"
    [ -f "$app" ] || return 0
    python3 - "$app" "$HOOK_BEGIN" "$HOOK_END" <<'PYEOF'
import sys
path, begin, end = sys.argv[1:]
src = open(path, encoding="utf-8").read()
while begin in src and end in src:
    start = src.index(begin)
    stop = src.index(end, start) + len(end)
    src = src[:start] + src[stop:].lstrip("\n")
open(path, "w", encoding="utf-8").write(src)
PYEOF
}

# Restart the console without killing ourselves: a direct `systemctl restart` from a child of
# the console's cgroup takes this script down with it (see InfraTAK-Module-MigrateAuthentik).
restart_console() {
    systemctl list-unit-files "$CONSOLE_SERVICE.service" >/dev/null 2>&1 || return 0
    if command -v systemd-run >/dev/null 2>&1; then
        systemd-run --no-block --collect --quiet -- systemctl restart "$CONSOLE_SERVICE" 2>/dev/null \
            && log "Console restart scheduled ($CONSOLE_SERVICE)" || warn "Restart $CONSOLE_SERVICE manually"
    else
        (systemctl restart "$CONSOLE_SERVICE" 2>/dev/null &)
    fi
}
