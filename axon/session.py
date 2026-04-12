"""Mining session persistence."""
import json

from axon.config import AXON_HOME

SESSIONS_DIR = AXON_HOME / "sessions"


def load_session(task_id: str) -> dict | None:
    path = SESSIONS_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_session(task_id: str, data: dict):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    (SESSIONS_DIR / f"{task_id}.json").write_text(json.dumps(data, indent=2))


def delete_session(task_id: str):
    path = SESSIONS_DIR / f"{task_id}.json"
    path.unlink(missing_ok=True)
