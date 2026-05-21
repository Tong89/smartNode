"""Backend entrypoint for SmartNode."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.api import app, run, simulation_engine  # noqa: E402


__all__ = ["app", "run", "simulation_engine"]


if __name__ == "__main__":
    run(host="127.0.0.1", port=5000, debug=False)
