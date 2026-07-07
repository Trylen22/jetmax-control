"""Shared repo paths for JetMax control scripts."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SAVED_POSITIONS_FILE = DATA_DIR / "saved_positions.json"
COORD_LOG_FILE = DATA_DIR / "jetmax_coord_log.csv"


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
