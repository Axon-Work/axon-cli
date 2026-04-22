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


def test_balance_zero_shows_free_cpu_hint():
    """Balance=$0 users see a panel telling them CPU tasks are FREE — fixes
    the common misconception that empty platform balance blocks all mining."""
    fake_me = {"address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12", "balance": 0}
    with patch("axon.cli.api_get", return_value=fake_me):
        result = runner.invoke(app, ["balance"])
    assert result.exit_code == 0
    assert "FREE" in result.output or "free" in result.output
    assert "axon mine" in result.output
    assert "axon deposit" in result.output


def test_balance_nonzero_hides_zero_hint():
    """Positive balance → no 'zero balance' panel clutter."""
    fake_me = {"address": "0xAbCdEf", "balance": 100}
    with patch("axon.cli.api_get", return_value=fake_me):
        result = runner.invoke(app, ["balance"])
    assert result.exit_code == 0
    assert "Zero balance" not in result.output


# ---------- _check_cli_available strict mode (E1) ----------

def test_check_cli_strict_aborts_when_missing(monkeypatch):
    """onboard passes strict=True. When the chosen CLI backend isn't on
    PATH, we must abort with Exit(1) so the user doesn't complete a setup
    that fails on first mine."""
    import shutil as _shutil
    import typer
    import pytest as _pytest
    from axon.cli import _check_cli_available
    monkeypatch.setattr(_shutil, "which", lambda name: None)
    with _pytest.raises(typer.Exit) as exc_info:
        _check_cli_available("claude-cli", _shutil, strict=True)
    assert exc_info.value.exit_code == 1


def test_check_cli_strict_passes_when_installed(monkeypatch):
    """Strict mode is a no-op when the tool is on PATH."""
    import shutil as _shutil
    from axon.cli import _check_cli_available
    monkeypatch.setattr(_shutil, "which", lambda name: "/usr/local/bin/" + name)
    _check_cli_available("claude-cli", _shutil, strict=True)
    _check_cli_available("codex-cli", _shutil, strict=True)
    _check_cli_available("litellm", _shutil, strict=True)  # no CLI tool to check


def test_check_cli_nonstrict_warns_only(monkeypatch):
    """Non-strict (default) must NOT abort — prints a warning and returns,
    so `axon backend claude-cli` can still flip config while tool is being
    installed."""
    import shutil as _shutil
    from axon.cli import _check_cli_available
    monkeypatch.setattr(_shutil, "which", lambda name: None)
    _check_cli_available("claude-cli", _shutil)   # no raise
    _check_cli_available("codex-cli", _shutil)


# ---------- axon mine ----------

def test_mine_no_tasks():
    """No open tasks → exit."""
    with patch("axon.cli.api_get", return_value=[]):
        result = runner.invoke(app, ["mine"])
    assert "No open tasks" in result.output


# The mine command opens an interactive simple_term_menu when --rounds /
# --timeout / --budget are not supplied. CliRunner has no tty, so tests
# must pass all three flags explicitly to avoid the menu (which would
# raise OSError: Device not configured at termios setup).
_FAKE_TASK = {
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


def test_mine_single_task():
    """mine starts immediately when there is a single open task."""
    with (
        patch("axon.cli.api_get", return_value=[_FAKE_TASK]),
        patch("axon.mining.run_mining") as mock_run_mining,
        patch("os.system", return_value=0),
    ):
        result = runner.invoke(app, ["mine", "--rounds", "5", "--timeout", "600", "--budget", "0"])
    assert result.exit_code == 0, result.output
    mock_run_mining.assert_called_once_with(_FAKE_TASK, 5, cli_timeout_override=600, budget=0.0)


def test_mine_unlimited():
    """--rounds 0 means unlimited; --timeout 0 means no hard cap."""
    with (
        patch("axon.cli.api_get", return_value=[_FAKE_TASK]),
        patch("axon.mining.run_mining") as mock_run_mining,
        patch("os.system", return_value=0),
    ):
        result = runner.invoke(app, ["mine", "--rounds", "0", "--timeout", "0", "--budget", "0"])
    assert result.exit_code == 0, result.output
    mock_run_mining.assert_called_once_with(_FAKE_TASK, 0, cli_timeout_override=None, budget=0.0)


def test_mine_custom_rounds():
    """--rounds N passes through to run_mining."""
    with (
        patch("axon.cli.api_get", return_value=[_FAKE_TASK]),
        patch("axon.mining.run_mining") as mock_run_mining,
        patch("os.system", return_value=0),
    ):
        result = runner.invoke(app, ["mine", "--rounds", "10", "--timeout", "600", "--budget", "0"])
    assert result.exit_code == 0, result.output
    mock_run_mining.assert_called_once_with(_FAKE_TASK, 10, cli_timeout_override=600, budget=0.0)


def test_mine_custom_timeout():
    """--timeout N passes through as cli_timeout_override."""
    with (
        patch("axon.cli.api_get", return_value=[_FAKE_TASK]),
        patch("axon.mining.run_mining") as mock_run_mining,
        patch("os.system", return_value=0),
    ):
        result = runner.invoke(app, ["mine", "--rounds", "5", "--timeout", "180", "--budget", "0"])
    assert result.exit_code == 0, result.output
    mock_run_mining.assert_called_once_with(_FAKE_TASK, 5, cli_timeout_override=180, budget=0.0)


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
