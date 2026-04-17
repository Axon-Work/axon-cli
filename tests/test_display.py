"""Tests for display module — verify Rich Table output."""
from io import StringIO

from rich.console import Console

from axon import display
from axon.theme import AXON_THEME


def _capture(fn, *args, **kwargs) -> str:
    """Run a display function with a captured console, return output text.

    Passes AXON_THEME so `[secondary]`, `[accent]`, `[money]` and other
    semantic styles resolve correctly — without it, Rich treats the style
    names as color names and raises MissingStyle.
    """
    buf = StringIO()
    orig = display.console
    display.console = Console(file=buf, no_color=True, width=120, theme=AXON_THEME)
    try:
        fn(*args, **kwargs)
    finally:
        display.console = orig
    return buf.getvalue()


# --- print_task_list ---

def test_print_task_list_renders_table():
    tasks = [
        {"id": "aaaa1111-2222-3333-4444-555566667777", "title": "Test Task",
         "eval_type": "exact_match", "best_score": 0.95, "pool_balance": 20000,
         "status": "open"},
        {"id": "bbbb1111-2222-3333-4444-555566667777", "title": "Another Task",
         "eval_type": "code_output", "best_score": None, "pool_balance": 50000,
         "status": "open"},
    ]
    out = _capture(display.print_task_list, tasks)
    assert "Test Task" in out
    assert "Another Task" in out
    assert "$200.00" in out  # 20000 cents = $200.00
    assert "$500.00" in out  # 50000 cents = $500.00
    assert "0.95" in out


def test_print_task_list_empty():
    out = _capture(display.print_task_list, [])
    assert "No tasks found" in out


# --- _fmt_usdc ---

def test_fmt_usdc_zero():
    assert display._fmt_usdc(0) == "$0.00"


def test_fmt_usdc_cents():
    assert display._fmt_usdc(1) == "$0.01"
    assert display._fmt_usdc(99) == "$0.99"


def test_fmt_usdc_dollars():
    assert display._fmt_usdc(150) == "$1.50"
    assert display._fmt_usdc(10000) == "$100.00"


# --- fmt_round ---

def test_fmt_round_improved():
    out = display.fmt_round(1, 0.5, "improved", 2000)
    assert "Round 1" in out
    assert "improved" in out
    assert "+$20.00" in out


def test_fmt_round_no_change():
    out = display.fmt_round(2, 0.3, "no change", 0)
    assert "Round 2" in out
    assert "no change" in out


def test_fmt_round_error():
    out = display.fmt_round(3, None, "error", 0)
    assert "Round 3" in out
    assert "error" in out


def test_fmt_round_completion():
    out = display.fmt_round(4, 1.0, "COMPLETE", 15000)
    assert "Round 4" in out
    assert "COMPLETE" in out
    assert "+$150.00" in out


def test_fmt_rounds_header():
    header = display.fmt_rounds_header()
    assert "Round" in header
    assert "Score" in header
    assert "Result" in header


# --- print_mining_summary ---

def test_print_mining_summary():
    rounds = [
        {"round": 1, "score": 0.5, "result": "improved", "earned": 2000},
        {"round": 4, "score": 1.0, "result": "COMPLETE", "earned": 15000},
    ]
    out = _capture(display.print_mining_summary, rounds, 1.0, 17000, 4)
    assert "Mining Summary" in out
    assert "$170.00" in out
    assert "1.000000" in out


def test_print_mining_summary_subscription_usage():
    rounds = [{"round": 1, "score": None, "result": "crash", "earned": 0}]
    out = _capture(
        display.print_mining_summary,
        rounds,
        None,
        0,
        1,
        total_tokens=None,
        total_cost=None,
        billing_mode="subscription",
    )
    assert "Tokens:  unknown" in out
    assert "Cost: subscription" in out


# --- print_stats ---

def test_print_stats():
    user = {"address": "0xAbCdEf1234567890AbCdEf1234567890AbCdEf12", "balance": 150000}
    breakdown = {"pool_reward": 80000, "completion_reward": 50000}
    out = _capture(display.print_stats, user, breakdown, 15)
    assert "$1500.00" in out  # balance
    assert "$800.00" in out   # pool_reward
    assert "$500.00" in out   # completion_reward
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
        pool=50000, threshold=1.0,
        best_score=0.5, total_earned=2000, round_count=1,
        status="", show_details=False, last_detail=None,
    )
    out = _render_panel(panel)
    assert "Answer 42" in out
    assert "claude-sonnet" in out
    assert "$500.00" in out
    assert "ctrl+o details" in out


def test_build_mining_panel_subscription_usage():
    panel = display.build_mining_panel(
        task_title="Header Codec",
        model="codex-cli",
        pool=50000,
        threshold=0.4,
        best_score=None,
        total_earned=0,
        round_count=3,
        status="",
        show_details=False,
        last_detail=None,
        total_tokens=None,
        total_cost=None,
        billing_mode="subscription",
    )
    out = _render_panel(panel)
    assert "Tokens: unknown" in out
    assert "Cost: subscription" in out


def test_build_mining_panel_with_details():
    detail = {
        "score": 0.75,
        "result": "improved",
        "earned": 2500,
        "error": None,
        "eval_details": {"stdout": "all tests passed"},
        "answer": "def solve(): return 42",
        "thinking": "I need to return 42",
    }
    rounds = [
        {"round": 1, "score": 0.3, "result": "no change", "earned": 0},
        {"round": 2, "score": 0.75, "result": "improved", "earned": 2500},
    ]
    panel = display.build_mining_panel(
        task_title="Code Task",
        model="openai/gpt-4", pool=30000, threshold=1.0,
        best_score=0.75, total_earned=1000, round_count=2,
        status="", show_details=True, last_detail=detail,
        rounds=rounds,
    )
    out = _render_panel(panel)
    # Rounds history
    assert "no change" in out
    assert "improved" in out
    assert "0.750000" in out
    assert "+$25.00" in out
    # Expanded details
    assert "Details" in out
    assert "all tests passed" in out
    assert "I need to return 42" in out
    assert "def solve" in out
    assert "ctrl+o close" in out
    assert "browse" in out


def test_time_ago():
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    assert display._time_ago((now - timedelta(seconds=30)).isoformat()) == "just now"
    assert display._time_ago((now - timedelta(minutes=5)).isoformat()) == "5m ago"
    assert display._time_ago((now - timedelta(hours=2)).isoformat()) == "2h ago"
    assert display._time_ago("") == ""


def test_fmt_community():
    subs = [
        {"miner_id": "aaaa1111-bbbb-cccc-dddd-eeee2222ffff", "score": 0.95,
         "llm_model_used": "anthropic/claude-sonnet", "created_at": ""},
        {"miner_id": "1111aaaa-2222-3333-4444-5555bbbb6666", "score": 0.80,
         "llm_model_used": "openai/gpt-4o", "created_at": ""},
    ]
    lines = display._fmt_community(subs, my_miner_id="1111aaaa-2222-3333-4444-5555bbbb6666")
    text = "\n".join(lines)
    assert "2 miners" in text
    assert "#1" in text
    assert "#2" in text
    assert "you" in text  # second one is me
    assert "0.9500" in text


def test_truncate_answer_basic():
    assert display._truncate_answer(None) == ""
    assert display._truncate_answer("") == ""
    assert display._truncate_answer("short answer") == "short answer"


def test_truncate_answer_newlines_and_long():
    ans = "line one\nline two\n\nline three"
    result = display._truncate_answer(ans)
    assert "\n" not in result
    assert result == "line one line two line three"
    # Long truncation
    long_ans = "x" * 200
    result = display._truncate_answer(long_ans, max_len=70)
    assert len(result) == 70
    assert result.endswith("\u2026")


def test_fmt_community_no_answer_preview():
    """Answer preview removed — community leaderboard only shows scores."""
    subs = [
        {"miner_id": "aaaa1111-bbbb-cccc-dddd-eeee2222ffff", "score": 0.95,
         "llm_model_used": "anthropic/claude-sonnet", "created_at": "",
         "answer": "def solve():\n    return 42"},
        {"miner_id": "1111aaaa-2222-3333-4444-5555bbbb6666", "score": 0.80,
         "llm_model_used": "openai/gpt-4o", "created_at": "",
         "answer": "The answer is 42"},
    ]
    lines = display._fmt_community(subs, my_miner_id="1111aaaa-2222-3333-4444-5555bbbb6666")
    text = "\n".join(lines)
    assert "def solve()" not in text             # answer preview removed
    assert "\u201c" not in text                   # no curly quotes
    assert "0.9500" in text                       # score still shown


def test_fmt_community_no_answer_field():
    subs = [{"miner_id": "aaaa-bbbb-cccc", "score": 0.90,
             "llm_model_used": "m", "created_at": ""}]
    lines = display._fmt_community(subs, my_miner_id="other")
    text = "\n".join(lines)
    assert "#1" in text
    assert "\u201c" not in text  # no quote = no preview


def test_fmt_community_no_answer_no_markup_leak():
    """With answer preview removed, Rich markup in answers can't leak."""
    subs = [{"miner_id": "aaaa1111-bbbb-cccc-dddd-eeee2222ffff", "score": 0.95,
             "llm_model_used": "m", "created_at": "",
             "answer": "[bold red]evil[/]"}]
    lines = display._fmt_community(subs, my_miner_id="other")
    text = "\n".join(lines)
    assert "bold red" not in text  # answer not shown at all


def test_build_mining_panel_with_community():
    subs = [
        {"miner_id": "aaaa-bbbb", "score": 0.9, "llm_model_used": "m", "created_at": "",
         "answer": "Hello world solution"},
    ]
    panel = display.build_mining_panel(
        task_title="T", model="m", pool=1000, threshold=1.0,
        best_score=0.5, total_earned=0, round_count=1,
        status="", show_details=False, last_detail=None,
        community_subs=subs, my_miner_id="xxxx",
    )
    out = _render_panel(panel)
    assert "Leaderboard" in out
    assert "1 miners" in out
    assert "Hello world solution" not in out  # answer preview removed


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
