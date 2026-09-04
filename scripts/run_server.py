"""Console-free local server runner for the scheduled logon task."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.runtime import RuntimePaths

# The local server log remains instance/server.log through the runtime path boundary.
LOG_PATH = RuntimePaths.for_project(ROOT).server_log


def configure_logging():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def local_server_state():
    try:
        with urlopen("http://127.0.0.1:5000", timeout=2) as response:
            page = response.read(4096).decode("utf-8", "replace")
            return "josh" if "Josh's Corner" in page else "other"
    except Exception:
        return "free"


def main():
    configure_logging()
    state = local_server_state()
    if state == "josh":
        logging.info("Josh's Corner is already running; hidden runner exited safely.")
        return 0
    if state == "other":
        logging.error("Port 5000 is occupied by another local service; hidden runner did not start.")
        return 1
    try:
        from app import create_app
        app = create_app()
        logging.info("Starting Josh's Corner on 127.0.0.1:5000.")
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    except Exception:
        logging.exception("Josh's Corner hidden server failed to start.")
        return 1
    finally:
        logging.info("Josh's Corner hidden server stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
