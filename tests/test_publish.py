"""Tests for CLI publish command."""
import json
import os
import tempfile
from unittest.mock import patch

from typer.testing import CliRunner

from axon.cli import app

runner = CliRunner()


FAKE_ME = {"address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12", "balance": 10000}
FAKE_TASK_RESULT = {
    "id": "aaaa-bbbb-cccc-dddd",
    "title": "Test Task",
    "pool_balance": 5000,
    "status": "open",
    "publisher_id": "1111-2222-3333-4444",
}


# ---------- JSON file mode ----------

def test_publish_from_json_file():
    """publish with a valid JSON file shows preview and posts to API."""
    task_data = {
        "title": "Sort Optimization",
        "description": "Write solve() that sorts",
        "eval_type": "code_output",
        "eval_config": {"setup_code": "print(solve())", "timeout": 30},
        "completion_threshold": 0.5,
        "pool_balance": 5000,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(task_data, f)
        tmp_path = f.name

    try:
        with (
            patch("axon.wallet.load_wallet", return_value={"address": "0x1234", "private_key": "0xkey"}),
            patch("axon.cli.api_get", return_value=FAKE_ME),
            patch("axon.cli.api_post", return_value=FAKE_TASK_RESULT),
        ):
            result = runner.invoke(app, ["publish", tmp_path], input="y\n")
        assert result.exit_code == 0
        assert "Task published" in result.output
    finally:
        os.unlink(tmp_path)


def test_publish_json_missing_fields():
    """publish with JSON missing required fields shows error."""
    task_data = {"title": "Incomplete"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(task_data, f)
        tmp_path = f.name

    try:
        with (
            patch("axon.wallet.load_wallet", return_value={"address": "0x1234", "private_key": "0xkey"}),
            patch("axon.cli.api_get", return_value=FAKE_ME),
        ):
            result = runner.invoke(app, ["publish", tmp_path])
        assert result.exit_code == 1
        assert "Missing required fields" in result.output
    finally:
        os.unlink(tmp_path)


def test_publish_json_file_not_found():
    """publish with nonexistent file shows error."""
    with (
        patch("axon.wallet.load_wallet", return_value={"address": "0x1234", "private_key": "0xkey"}),
        patch("axon.cli.api_get", return_value=FAKE_ME),
    ):
        result = runner.invoke(app, ["publish", "/tmp/nonexistent_axon_task.json"])
    assert result.exit_code == 1
    assert "File not found" in result.output


# ---------- Error cases ----------

def test_publish_no_wallet():
    """publish without wallet shows onboard prompt."""
    with patch("axon.wallet.load_wallet", return_value=None):
        result = runner.invoke(app, ["publish"])
    assert result.exit_code == 1
    assert "No wallet" in result.output


def test_publish_zero_balance():
    """publish with zero balance shows error."""
    zero_me = {"address": "0xAbCd", "balance": 0}
    with (
        patch("axon.wallet.load_wallet", return_value={"address": "0x1234", "private_key": "0xkey"}),
        patch("axon.cli.api_get", return_value=zero_me),
    ):
        result = runner.invoke(app, ["publish"])
    assert result.exit_code == 1
    assert "No balance" in result.output


def test_publish_pool_exceeds_balance():
    """publish with pool > balance shows error before API call."""
    low_balance = {"address": "0xAbCd", "balance": 1000}
    task_data = {
        "title": "Too Expensive",
        "description": "Needs more money",
        "eval_type": "exact_match",
        "eval_config": {"expected": "42"},
        "completion_threshold": 1.0,
        "pool_balance": 5000,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(task_data, f)
        tmp_path = f.name

    try:
        with (
            patch("axon.wallet.load_wallet", return_value={"address": "0x1234", "private_key": "0xkey"}),
            patch("axon.cli.api_get", return_value=low_balance),
        ):
            result = runner.invoke(app, ["publish", tmp_path])
        assert result.exit_code == 1
        assert "exceeds balance" in result.output
    finally:
        os.unlink(tmp_path)


def test_publish_user_cancels():
    """publish cancelled at confirmation → clean exit."""
    task_data = {
        "title": "Will Cancel",
        "description": "Not going to publish",
        "eval_type": "exact_match",
        "eval_config": {"expected": "42"},
        "completion_threshold": 1.0,
        "pool_balance": 5000,
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(task_data, f)
        tmp_path = f.name

    try:
        with (
            patch("axon.wallet.load_wallet", return_value={"address": "0x1234", "private_key": "0xkey"}),
            patch("axon.cli.api_get", return_value=FAKE_ME),
        ):
            result = runner.invoke(app, ["publish", tmp_path], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output
    finally:
        os.unlink(tmp_path)
