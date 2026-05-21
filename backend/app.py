"""Separated backend entrypoint.

The simulation engine is still kept in the legacy-compatible root ``main.py``
for now. This module exposes the Flask app from the backend package so the
project can be run as ``python backend/app.py`` while the frontend lives under
``frontend/``.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app, simulation_engine  # noqa: E402


__all__ = ["app", "simulation_engine"]


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)
