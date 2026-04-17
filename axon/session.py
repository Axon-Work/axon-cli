"""Mining session persistence."""
import json

from axon._fs import atomic_write_json
from axon.config import AXON_HOME

SESSIONS_DIR = AXON_HOME / "sessions"


def load_session(task_id: str) -> dict | None:
    path = SESSIONS_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def save_session(task_id: str, data: dict):
    atomic_write_json(SESSIONS_DIR / f"{task_id}.json", data)


def delete_session(task_id: str):
    path = SESSIONS_DIR / f"{task_id}.json"
    path.unlink(missing_ok=True)
