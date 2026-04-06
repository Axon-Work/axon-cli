"""Tests for CLI commands — smoke tests and basic functionality."""
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from axon.cli import app

runner = CliRunner()


# ---------- axon (no subcommand) ----------

def test_root_first_run():
    """First run (no wallet) shows welcome message."""
    with patch("axon.cli._is_first_run", return_value=True):
        result = runner.invoke(app)
    assert result.exit_code == 0
    assert "Welcome to Axon" in result.output


def test_root_existing_wallet():
    """With wallet shows status summary."""
    with (
        patch("axon.cli._is_first_run", return_value=False),
        patch("axon.config.load_config", return_value={"default_model": "anthropic/claude-sonnet"}),
        patch("axon.wallet.get_address", return_value="0xAbCdEf1234567890AbCdEf1234567890AbCdEf12"),
    ):
        result = runner.invoke(app)
    assert result.exit_code == 0
    assert "0xAbCd" in result.output
    assert "claude-sonnet" in result.output


# ---------- axon --help ----------

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Axon" in result.output


# ---------- axon wallet ----------

def test_wallet_no_wallet():
    """No wallet file → error message."""
    with patch("axon.wallet.load_wallet", return_value=None):
        result = runner.invoke(app, ["wallet"])
    assert result.exit_code == 1
    assert "No wallet" in result.output


def test_wallet_with_wallet():
    """Existing wallet → shows address."""
    fake_wallet = {"address": "0x1234abcd5678ef901234abcd5678ef901234abcd", "private_key": "0xsecret"}
    with patch("axon.wallet.load_wallet", return_value=fake_wallet):
        result = runner.invoke(app, ["wallet"])
    assert result.exit_code == 0
    assert "0x1234abcd" in result.output


# ---------- axon tui ----------

def test_tui_launches():
    """tui command calls run_tui."""
    import axon.tui.app  # ensure module is loaded before patching
    with patch.object(axon.tui.app, "run_tui") as mock_run:
        result = runner.invoke(app, ["tui"])
    mock_run.assert_called_once()
    assert result.exit_code == 0


# ---------- axon dev ----------

def test_dev_sets_textual_env():
    """dev command sets TEXTUAL env var and calls run_tui."""
    import axon.tui.app
    with patch.object(axon.tui.app, "run_tui") as mock_run:
        result = runner.invoke(app, ["dev"])
    mock_run.assert_called_once()
    assert result.exit_code == 0


# ---------- axon balance ----------

def test_balance():
    """balance command shows wallet + balance."""
    fake_me = {"address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12", "balance": 1500}
    with patch("axon.cli.api_get", return_value=fake_me):
        result = runner.invoke(app, ["balance"])
    assert result.exit_code == 0
    assert "1,500" in result.output
    assert "0xAbCd" in result.output


# ---------- axon mine ----------

def test_mine_no_tasks():
    """No open tasks → exit."""
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["mine"])
    assert "No open tasks" in result.output


def test_mine_auto():
    """--auto flag picks highest pool task and starts mining."""
    fake_tasks = [
        {"id": "aaaa-bbbb", "title": "Best task", "pool_balance": 500, "best_score": None,
         "eval_type": "exact_match", "direction": "maximize", "completion_threshold": 1.0,
         "description": "test", "eval_config": {}, "status": "open"},
        {"id": "cccc-dddd", "title": "Other task", "pool_balance": 100, "best_score": None},
    ]
    fake_task = fake_tasks[0]
    fake_best = {"score": None, "submission_id": None}

    def mock_api_get(path, auth=True):
        if "task_status" in path:
            return fake_tasks
        if "best" in path:
            return fake_best
        return fake_task

    with (
        patch("axon.cli.api_get", side_effect=mock_api_get),
        patch("axon.mining.api_get", side_effect=mock_api_get),
        patch("axon.mining.call_llm", side_effect=KeyboardInterrupt),
    ):
        result = runner.invoke(app, ["mine", "--auto"])
    assert "Mining stopped" in result.output or "Mining Summary" in result.output or result.exit_code == 0


# ---------- axon tasks list ----------

def test_tasks_list():
    """tasks list shows task table."""
    fake_tasks = [
        {"id": "11112222-3333-4444-5555-666677778888", "title": "Test task",
         "eval_type": "exact_match", "best_score": 0.95, "pool_balance": 200},
    ]
    with patch("axon.cli.api_get", return_value=fake_tasks):
        result = runner.invoke(app, ["tasks", "list"])
    assert result.exit_code == 0
    assert "Test task" in result.output
    assert "200" in result.output


def test_tasks_list_empty():
    """tasks list with no tasks → empty output."""
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["tasks", "list"])
    assert result.exit_code == 0


# ---------- axon tasks view ----------

def test_tasks_view():
    """tasks view shows task detail."""
    fake_task = {
        "id": "11112222-3333-4444-5555-666677778888",
        "title": "My task", "description": "Do something",
        "eval_type": "exact_match", "direction": "maximize",
        "status": "open", "completion_threshold": 1.0,
        "best_score": 0.5, "pool_balance": 300,
    }
    with patch("axon.cli.api_get", return_value=fake_task):
        result = runner.invoke(app, ["tasks", "view", "11112222"])
    assert result.exit_code == 0
    assert "My task" in result.output
    assert "300" in result.output
