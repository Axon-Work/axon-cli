"""Tests for display module — verify Rich Table output."""
from io import StringIO

from rich.console import Console

from axon import display


def _capture(fn, *args, **kwargs) -> str:
    """Run a display function with a captured console, return output text."""
    buf = StringIO()
    orig = display.console
    display.console = Console(file=buf, no_color=True, width=120)
    try:
        fn(*args, **kwargs)
    finally:
        display.console = orig
    return buf.getvalue()


# --- print_tasks ---

def test_print_tasks_renders_table():
    tasks = [
        {"id": "aaaa1111-2222-3333-4444-555566667777", "title": "Test Task",
         "eval_type": "exact_match", "best_score": 0.95, "pool_balance": 200},
        {"id": "bbbb1111-2222-3333-4444-555566667777", "title": "Another Task",
         "eval_type": "code_output", "best_score": None, "pool_balance": 500},
    ]
    out = _capture(display.print_tasks, tasks, "Open Tasks")
    assert "Test Task" in out
    assert "Another Task" in out
    assert "200 $AXN" in out
    assert "500 $AXN" in out
    assert "0.95" in out


def test_print_tasks_empty():
    out = _capture(display.print_tasks, [], "Empty")
    assert "Empty" in out


# --- print_task_detail ---

def test_print_task_detail():
    task = {
        "id": "aaaa1111-2222-3333-4444-555566667777",
        "title": "My Task", "description": "Do the thing",
        "eval_type": "exact_match", "direction": "maximize",
        "status": "open", "completion_threshold": 1.0,
        "best_score": 0.5, "pool_balance": 300,
    }
    out = _capture(display.print_task_detail, task)
    assert "My Task" in out
    assert "aaaa1111" in out
    assert "exact_match" in out
    assert "300 $AXN" in out
    assert "Do the thing" in out


# --- fmt_round ---

def test_fmt_round_improved():
    out = display.fmt_round(1, 0.5, "improved", 20)
    assert "improved" in out
    assert "+20 $AXN" in out


def test_fmt_round_no_change():
    out = display.fmt_round(2, 0.3, "no change", 0)
    assert "no change" in out


def test_fmt_round_error():
    out = display.fmt_round(3, None, "error", 0)
    assert "error" in out


def test_fmt_round_completion():
    out = display.fmt_round(4, 1.0, "COMPLETE", 150)
    assert "COMPLETE" in out
    assert "+150 $AXN" in out


# --- print_mining_summary ---

def test_print_mining_summary():
    rounds = [
        {"round": 1, "score": 0.5, "result": "improved", "earned": 20},
        {"round": 4, "score": 1.0, "result": "COMPLETE", "earned": 150},
    ]
    out = _capture(display.print_mining_summary, rounds, 1.0, 170, 4)
    assert "Mining Summary" in out
    assert "170" in out
    assert "1.000000" in out


# --- print_stats ---

def test_print_stats():
    user = {"address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12", "balance": 1500}
    out = _capture(display.print_stats, user, 2000, 500, 15)
    assert "1,500" in out
    assert "2,000" in out
    assert "500" in out
    assert "15" in out


# --- build_mining_panel ---

def _render_panel(panel) -> str:
    """Render a Rich Panel to plain text."""
    buf = StringIO()
    c = Console(file=buf, no_color=True, width=100)
    c.print(panel)
    return buf.getvalue()


def test_build_mining_panel_basic():
    panel = display.build_mining_panel(
        task_title="Answer 42",
        model="anthropic/claude-sonnet",
        pool=500, threshold=1.0,
        best_score=0.5, total_earned=20, round_count=1,
        status="", show_details=False, last_detail=None,
    )
    out = _render_panel(panel)
    assert "Answer 42" in out
    assert "claude-sonnet" in out
    assert "500 $AXN" in out
    assert "ctrl+o details" in out


def test_build_mining_panel_with_details():
    detail = {
        "score": 0.75,
        "result": "improved",
        "earned": 25,
        "error": None,
        "eval_details": {"stdout": "all tests passed"},
        "answer": "def solve(): return 42",
        "thinking": "I need to return 42",
    }
    rounds = [
        {"round": 1, "score": 0.3, "result": "no change", "earned": 0},
        {"round": 2, "score": 0.75, "result": "improved", "earned": 25},
    ]
    panel = display.build_mining_panel(
        task_title="Code Task",
        model="openai/gpt-4", pool=300, threshold=1.0,
        best_score=0.75, total_earned=10, round_count=2,
        status="", show_details=True, last_detail=detail,
        rounds=rounds,
    )
    out = _render_panel(panel)
    # Rounds history
    assert "no change" in out
    assert "improved" in out
    assert "0.750000" in out
    assert "+25 $AXN" in out
    # Expanded details
    assert "Details" in out
    assert "all tests passed" in out
    assert "I need to return 42" in out
    assert "def solve" in out
    assert "ctrl+o close" in out
    assert "browse" in out


def test_build_mining_panel_details_hidden():
    rounds = [{"round": 1, "score": 0.5, "result": "no change", "earned": 0}]
    panel = display.build_mining_panel(
        task_title="T", model="m", pool=0, threshold=1.0,
        best_score=None, total_earned=0, round_count=1,
        status="", show_details=False, last_detail=None,
        rounds=rounds,
    )
    out = _render_panel(panel)
    # Rounds history always visible
    assert "no change" in out
    # But expanded details are hidden
    assert "Details" not in out
    assert "ctrl+o details" in out
