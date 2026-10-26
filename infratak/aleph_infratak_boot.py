"""Loaded at interpreter start by aleph_infratak.pth in the infra-TAK console's site-packages.

Why not patch app.py like the sibling modules? infra-TAK's "Update Now" runs
`git checkout --force <tag>`, which silently discards every edit to app.py — and the text
anchors those patches need differ between releases. Instead this installs an import hook:
when the console's `app` module finishes loading (gunicorn imports `app:app`), attach() adds
Aleph's routes and card to the live objects. Nothing tracked by infra-TAK's git is touched, so
updates neither remove it nor conflict with it.

Fails closed: any error here is printed and swallowed — the console always starts.
Opt out without uninstalling: ALEPH_DISABLE_CONSOLE_HOOK=1 in the console's environment.
"""

import importlib.abc
import importlib.machinery
import os
import sys


def _is_infratak(origin):
    """infra-TAK's app.py sits next to its start.sh launcher in every release."""
    if not origin or os.path.basename(origin) != "app.py":
        return False
    return os.path.isfile(os.path.join(os.path.dirname(origin), "start.sh"))


class AlephConsoleFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "app":
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None or not _is_infratak(spec.origin):
            return None
        original = spec.loader.exec_module

        def exec_module(module):
            original(module)
            try:
                import aleph_infratak
                aleph_infratak.attach(module)
            except Exception as error:  # the console must start even if Aleph's hook is broken
                print(f"[aleph-tak] console hook skipped: {error!r}", file=sys.stderr, flush=True)

        spec.loader.exec_module = exec_module
        return spec


if os.environ.get("ALEPH_DISABLE_CONSOLE_HOOK") != "1" and not any(
        type(finder).__name__ == "AlephConsoleFinder" for finder in sys.meta_path):
    sys.meta_path.insert(0, AlephConsoleFinder())
