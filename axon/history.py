"""Mining history persistence — JSONL-based per-task history."""
import json
import logging
from datetime import datetime, timezone

from axon._fs import atomic_append_jsonl
from axon.config import AXON_HOME

HISTORY_DIR = AXON_HOME / "history"

log = logging.getLogger("axon.history")


def load_history(task_id: str) -> list[dict]:
    """Read all records from the JSONL file, skipping corrupt lines."""
    path = HISTORY_DIR / f"{task_id}.jsonl"
    if not path.exists():
        return []
    records = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("Corrupt line %d in %s, skipping", lineno, path)
    return records


def append_record(task_id: str, record: dict) -> None:
    """Append a single JSON record to the task's history file."""
    atomic_append_jsonl(HISTORY_DIR / f"{task_id}.jsonl", record)


def merge_server_history(task_id: str, server_subs: list[dict]) -> list[dict]:
    """Load local history, merge in server submissions (dedup by id), return combined list."""
    local = load_history(task_id)
    local_ids = {r["id"] for r in local if r.get("id")}

    for sub in server_subs:
        sub_id = sub.get("id")
        if not sub_id or sub_id in local_ids:
            continue
        record = {
            "id": sub_id,
            "score": sub.get("score"),
            "eval_status": sub.get("eval_status"),
            "eval_error": sub.get("eval_error"),
            "eval_details": sub.get("eval_details"),
            "is_improvement": sub.get("is_improvement"),
            "is_completion": sub.get("is_completion", False),
            "reward_earned": sub.get("reward_earned", 0),
            "llm_model_used": sub.get("llm_model_used"),
            "created_at": sub.get("created_at", ""),
            "answer": None,
            "thinking": None,
            "billing_mode": "unknown",
            "tokens": None,
            "cost_usd": None,
            "cost": None,
            "round_num": None,
            "result_label": None,
            "source": "server",
        }
        append_record(task_id, record)
        local.append(record)

    return local


def build_local_record(sub: dict, answer: str, thinking: str,
                       tokens: int | None, cost: float | None, round_num: int,
                       billing_mode: str,
                       result_label: str) -> dict:
    """Build a complete history record from a successful submission."""
    return {
        "id": sub.get("id"),
        "score": sub.get("score"),
        "eval_status": sub.get("eval_status"),
        "eval_error": sub.get("eval_error"),
        "eval_details": sub.get("eval_details"),
        "is_improvement": sub.get("is_improvement"),
        "is_completion": sub.get("is_completion", False),
        "reward_earned": sub.get("reward_earned", 0),
        "llm_model_used": sub.get("llm_model_used"),
        "created_at": sub.get("created_at", ""),
        "answer": answer,
        "thinking": thinking,
        "billing_mode": billing_mode,
        "tokens": tokens,
        "cost_usd": cost,
        "cost": cost,
        "round_num": round_num,
        "result_label": result_label,
        "source": "local",
    }


def build_error_record(task_id: str, answer: str | None, thinking: str | None,
                       tokens: int | None, cost: float | None, round_num: int,
                       billing_mode: str,
                       result_label: str, error: str) -> dict:
    """Build a history record for a failed round (no server response)."""
    return {
        "id": None,
        "score": None,
        "eval_status": "error",
        "eval_error": error,
        "eval_details": None,
        "is_improvement": None,
        "is_completion": False,
        "reward_earned": 0,
        "llm_model_used": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "answer": answer,
        "thinking": thinking,
        "billing_mode": billing_mode,
        "tokens": tokens,
        "cost_usd": cost,
        "cost": cost,
        "round_num": round_num,
        "result_label": result_label,
        "source": "local",
    }


def delete_history(task_id: str) -> None:
    """Delete a task's history file."""
    path = HISTORY_DIR / f"{task_id}.jsonl"
    path.unlink(missing_ok=True)
