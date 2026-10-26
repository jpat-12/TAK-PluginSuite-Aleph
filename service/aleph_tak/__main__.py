"""Command line: `python -m aleph_tak <command>` (installed as /usr/local/bin/aleph-tak).

    serve                     run the HTTP service (what the systemd unit runs)
    create-token NAME [ROLE]  print a new API token (ROLE: client | proxy)
    set-admin-password        set the local /admin password (prompts, or reads stdin)
    show-config               print effective settings (secrets omitted)
"""

import getpass
import json
import logging
import sys

from . import __version__


def serve():
    from waitress import serve as waitress_serve

    from .app import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app()
    config = app.extensions["aleph"]["config"]
    host, _, port = config["listen"].rpartition(":")
    logging.getLogger("aleph-tak").info("[aleph-tak] v%s listening on %s (data: %s)", __version__,
                                        config["listen"], config.data_dir)
    # Package downloads are large and phones are slow: generous channel timeout, enough threads
    # that a few long downloads can't starve API polling.
    waitress_serve(app, host=host or "127.0.0.1", port=int(port), threads=16, channel_timeout=600,
                   ident=f"aleph-tak/{__version__}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv else "serve"
    if command == "serve":
        return serve()
    from .config import Config
    config = Config()
    if command == "create-token":
        from .auth import Tokens
        if not argv:
            sys.exit("usage: aleph-tak create-token NAME [client|proxy]")
        print(Tokens(config.data_dir / "tokens.json").create(argv[0], argv[1] if len(argv) > 1 else "client"))
    elif command == "set-admin-password":
        from werkzeug.security import generate_password_hash
        password = sys.stdin.readline().strip() if not sys.stdin.isatty() else getpass.getpass("New admin password: ")
        if len(password) < 10:
            sys.exit("Use at least 10 characters.")
        config.secrets["admin_password_hash"] = generate_password_hash(password)
        config.save_secrets()
        print("Admin password set.")
    elif command == "show-config":
        print(json.dumps(dict(version=__version__, data_dir=str(config.data_dir), settings=config.settings), indent=2))
    elif command in ("-h", "--help", "help"):
        print(__doc__)
    else:
        sys.exit(f"Unknown command: {command}\n{__doc__}")


if __name__ == "__main__":
    main()
