from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

_lock = Lock()

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "runtime"
STATE_FILE = STATE_DIR / "current_upload.json"

STATE_DIR.mkdir(parents=True, exist_ok=True)


def set_uploaded(filename, result, readings=None):
    payload = {
        "filename": filename,
        "result": result,
        "readings": readings or [],
    }

    with _lock:
        STATE_FILE.write_text(
            json.dumps(payload, default=str, indent=2),
            encoding="utf-8",
        )


def get_uploaded():
    with _lock:
        if not STATE_FILE.exists():
            return None

        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None


def clear_uploaded():
    with _lock:
        if STATE_FILE.exists():
            STATE_FILE.unlink()