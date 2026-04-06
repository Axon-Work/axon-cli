"""Tests for session persistence."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from axon.session import load_session, save_session, delete_session


def test_load_nonexistent(tmp_path):
    with patch("axon.session.SESSIONS_DIR", tmp_path):
        assert load_session("nonexistent-id") is None


def test_save_and_load(tmp_path):
    with patch("axon.session.SESSIONS_DIR", tmp_path):
        data = {"my_best_answer": "42", "my_best_score": 1.0, "round_num": 3, "total_earned": 100}
        save_session("task-123", data)
        loaded = load_session("task-123")
        assert loaded["my_best_answer"] == "42"
        assert loaded["my_best_score"] == 1.0
        assert loaded["round_num"] == 3


def test_delete_session(tmp_path):
    with patch("axon.session.SESSIONS_DIR", tmp_path):
        save_session("task-456", {"round_num": 1})
        assert load_session("task-456") is not None
        delete_session("task-456")
        assert load_session("task-456") is None


def test_delete_nonexistent(tmp_path):
    with patch("axon.session.SESSIONS_DIR", tmp_path):
        delete_session("does-not-exist")  # should not raise


def test_corrupt_session(tmp_path):
    with patch("axon.session.SESSIONS_DIR", tmp_path):
        (tmp_path / "bad.json").write_text("not json")
        assert load_session("bad") is None
