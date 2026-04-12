"""Tests for mining history persistence."""
import json

from axon.history import (
    load_history, append_record, merge_server_history,
    build_local_record, build_error_record, delete_history,
    HISTORY_DIR,
)


def test_load_history_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    assert load_history("nonexistent") == []


def test_load_history_empty_file(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    (tmp_path / "task-1.jsonl").write_text("")
    assert load_history("task-1") == []


def test_append_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    record = {"id": "abc", "score": 0.5, "answer": "hello"}
    append_record("task-1", record)
    append_record("task-1", {"id": "def", "score": 0.8, "answer": "world"})

    loaded = load_history("task-1")
    assert len(loaded) == 2
    assert loaded[0]["id"] == "abc"
    assert loaded[1]["answer"] == "world"


def test_load_history_skips_corrupt_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    content = json.dumps({"id": "good", "score": 1.0}) + "\n"
    content += "not valid json\n"
    content += json.dumps({"id": "also-good", "score": 2.0}) + "\n"
    (tmp_path / "task-1.jsonl").write_text(content)

    loaded = load_history("task-1")
    assert len(loaded) == 2
    assert loaded[0]["id"] == "good"
    assert loaded[1]["id"] == "also-good"


def test_merge_server_history_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    # Pre-populate local with one record
    append_record("task-1", {"id": "aaa", "score": 0.5, "source": "local", "answer": "my answer"})

    server_subs = [
        {"id": "aaa", "score": 0.5, "eval_status": "completed"},  # already local
        {"id": "bbb", "score": 0.7, "eval_status": "completed"},  # new
    ]
    result = merge_server_history("task-1", server_subs)

    assert len(result) == 2
    # Local record preserved with answer
    assert result[0]["answer"] == "my answer"
    # Server record appended without answer
    assert result[1]["id"] == "bbb"
    assert result[1]["answer"] is None
    assert result[1]["source"] == "server"

    # Verify file has 2 lines
    lines = (tmp_path / "task-1.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2


def test_merge_server_history_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    result = merge_server_history("task-1", [])
    assert result == []


def test_build_local_record():
    sub = {
        "id": "uuid-1",
        "score": 0.85,
        "eval_status": "completed",
        "eval_error": None,
        "eval_details": {"stdout": "ok"},
        "is_improvement": True,
        "is_completion": False,
        "reward_earned": 100,
        "llm_model_used": "test-model",
        "created_at": "2025-01-01T00:00:00Z",
    }
    record = build_local_record(sub, "my answer", "my thinking", 1000, 0.05, 3, "metered", "improved")

    assert record["id"] == "uuid-1"
    assert record["score"] == 0.85
    assert record["answer"] == "my answer"
    assert record["thinking"] == "my thinking"
    assert record["billing_mode"] == "metered"
    assert record["tokens"] == 1000
    assert record["cost_usd"] == 0.05
    assert record["cost"] == 0.05
    assert record["round_num"] == 3
    assert record["result_label"] == "improved"
    assert record["source"] == "local"


def test_build_error_record():
    record = build_error_record("task-1", "bad code", "my thinking", 500, 0.02, 2, "metered", "crash", "SyntaxError")

    assert record["id"] is None
    assert record["score"] is None
    assert record["eval_status"] == "error"
    assert record["eval_error"] == "SyntaxError"
    assert record["answer"] == "bad code"
    assert record["thinking"] == "my thinking"
    assert record["billing_mode"] == "metered"
    assert record["tokens"] == 500
    assert record["cost_usd"] == 0.02
    assert record["round_num"] == 2
    assert record["result_label"] == "crash"
    assert record["source"] == "local"
    assert record["created_at"]  # non-empty


def test_build_error_record_subscription_usage():
    record = build_error_record("task-1", None, None, None, None, 1, "subscription", "crash", "timeout")

    assert record["billing_mode"] == "subscription"
    assert record["tokens"] is None
    assert record["cost_usd"] is None
    assert record["cost"] is None


def test_delete_history(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    append_record("task-1", {"id": "x"})
    assert (tmp_path / "task-1.jsonl").exists()

    delete_history("task-1")
    assert not (tmp_path / "task-1.jsonl").exists()


def test_delete_history_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("axon.history.HISTORY_DIR", tmp_path)
    delete_history("nonexistent")  # should not raise
