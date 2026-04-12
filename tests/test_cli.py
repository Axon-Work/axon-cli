"""Tests for CLI commands — smoke tests and basic functionality."""
from unittest.mock import patch

from typer.testing import CliRunner

from axon.cli import app

runner = CliRunner()


# ---------- axon (no subcommand) ----------

def test_root_first_run():
    """First run (no wallet) shows welcome message."""
    with patch("axon.cli._is_first_run", return_value=True):
        result = runner.invoke(app)
    assert result.exit_code == 0
    assert "A X O N" in result.output
    assert "axon tui" not in result.output


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
    assert "axon tui" not in result.output


# ---------- axon --help ----------

def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Axon" in result.output
    assert "tui" not in result.output


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

# ---------- axon balance ----------

def test_tui_command_removed():
    """tui command is no longer available."""
    result = runner.invoke(app, ["tui"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_balance():
    """balance command shows wallet + balance."""
    fake_me = {"address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12", "balance": 1500}
    with patch("axon.cli.api_get", return_value=fake_me):
        result = runner.invoke(app, ["balance"])
    assert result.exit_code == 0
    assert "$15.00" in result.output
    assert "0xAbCd" in result.output


# ---------- axon mine ----------

def test_mine_no_tasks():
    """No open tasks → exit."""
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["mine"])
    assert "No open tasks" in result.output


def test_mine_single_task():
    """mine starts immediately when there is a single open task."""
    fake_task = {
        "id": "aaaa-bbbb",
        "title": "Best task",
        "pool_balance": 500,
        "best_score": None,
        "eval_type": "exact_match",
        "direction": "maximize",
        "completion_threshold": 1.0,
        "description": "test",
        "eval_config": {},
        "status": "open",
    }

    with (
        patch("axon.cli.api_get", return_value=[fake_task]),
        patch("axon.mining.run_mining") as mock_run_mining,
        patch("os.system", return_value=0),
    ):
        result = runner.invoke(app, ["mine"])
    assert result.exit_code == 0
    mock_run_mining.assert_called_once_with(fake_task, 5, cli_timeout_override=600)


def test_mine_yolo_single_task():
    """mine --yolo disables hard timeout and round limit for this run."""
    fake_task = {
        "id": "aaaa-bbbb",
        "title": "Best task",
        "pool_balance": 500,
        "best_score": None,
        "eval_type": "exact_match",
        "direction": "maximize",
        "completion_threshold": 1.0,
        "description": "test",
        "eval_config": {},
        "status": "open",
    }

    with (
        patch("axon.cli.api_get", return_value=[fake_task]),
        patch("axon.mining.run_mining") as mock_run_mining,
    ):
        result = runner.invoke(app, ["mine", "--yolo"])
    assert result.exit_code == 0
    mock_run_mining.assert_called_once_with(fake_task, 0, cli_timeout_override=None)


def test_mine_yolo_single_dash_alias():
    """mine -yolo is accepted as an alias for --yolo."""
    fake_task = {
        "id": "aaaa-bbbb",
        "title": "Best task",
        "pool_balance": 500,
        "best_score": None,
        "eval_type": "exact_match",
        "direction": "maximize",
        "completion_threshold": 1.0,
        "description": "test",
        "eval_config": {},
        "status": "open",
    }

    with (
        patch("axon.cli.api_get", return_value=[fake_task]),
        patch("axon.mining.run_mining") as mock_run_mining,
    ):
        result = runner.invoke(app, ["mine", "-yolo"])
    assert result.exit_code == 0
    mock_run_mining.assert_called_once_with(fake_task, 0, cli_timeout_override=None)


def test_mine_yolo_conflicts_with_max_rounds():
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["mine", "--yolo", "--max-rounds", "10"])
    assert result.exit_code == 1
    assert "Cannot combine --yolo with --max-rounds" in result.output


def test_mine_yolo_conflicts_with_timeout():
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["mine", "--yolo", "--timeout", "180"])
    assert result.exit_code == 1
    assert "Cannot combine --yolo with --timeout" in result.output


def test_mine_custom_max_rounds():
    """mine --max-rounds overrides the default round cap but keeps the default timeout."""
    fake_task = {
        "id": "aaaa-bbbb",
        "title": "Best task",
        "pool_balance": 500,
        "best_score": None,
        "eval_type": "exact_match",
        "direction": "maximize",
        "completion_threshold": 1.0,
        "description": "test",
        "eval_config": {},
        "status": "open",
    }

    with (
        patch("axon.cli.api_get", return_value=[fake_task]),
        patch("axon.mining.run_mining") as mock_run_mining,
    ):
        result = runner.invoke(app, ["mine", "--max-rounds", "10"])
    assert result.exit_code == 0
    mock_run_mining.assert_called_once_with(fake_task, 10, cli_timeout_override=600)


def test_mine_custom_timeout():
    """mine --timeout overrides the default hard timeout but keeps the default round cap."""
    fake_task = {
        "id": "aaaa-bbbb",
        "title": "Best task",
        "pool_balance": 500,
        "best_score": None,
        "eval_type": "exact_match",
        "direction": "maximize",
        "completion_threshold": 1.0,
        "description": "test",
        "eval_config": {},
        "status": "open",
    }

    with (
        patch("axon.cli.api_get", return_value=[fake_task]),
        patch("axon.mining.run_mining") as mock_run_mining,
    ):
        result = runner.invoke(app, ["mine", "--timeout", "180"])
    assert result.exit_code == 0
    mock_run_mining.assert_called_once_with(fake_task, 5, cli_timeout_override=180)


# ---------- axon tasks list ----------

def test_tasks_list():
    """tasks list shows task table."""
    fake_tasks = [
        {"id": "11112222-3333-4444-5555-666677778888", "title": "Test task",
         "eval_type": "exact_match", "best_score": 0.95, "pool_balance": 200},
    ]
    with patch("axon.cli.api_get", return_value=fake_tasks):
        result = runner.invoke(app, ["tasks"])
    assert result.exit_code == 0
    assert "Test task" in result.output
    assert "$2.00" in result.output


def test_tasks_list_empty():
    """tasks list with no tasks → empty output."""
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["tasks"])
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
        result = runner.invoke(app, ["task", "11112222-3333-4444-5555-666677778888"])
    assert result.exit_code == 0
    assert "My task" in result.output
    assert "$3.00" in result.output
