"""Rich display helpers — all CLI formatting lives here."""
import re

from rich.align import Align
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from axon.theme import (
    console, branded_title, status_dot,
    GOLD, PRIMARY_BOX, TABLE_BOX,
)

BRAILLE_FRAMES = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"


def print_banner() -> None:
    from rich.text import Text
    lines = Text(justify="center")
    lines.append("\u03a8  A X O N", style="brand")
    lines.append("\n")
    lines.append("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500", style="secondary")
    lines.append("\n")
    lines.append("World Intelligence", style="secondary")
    lines.append("\n")
    lines.append("Proof of Useful Work", style="dim")
    panel = Panel(lines, box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2))
    console.print()
    console.print(panel)
    console.print()


def _fmt_usdc(cents: int) -> str:
    """Format USDC cents as dollar string."""
    return f"${cents / 100:.2f}"


def _format_usage_summary(
    total_tokens: int | None = 0,
    total_cost: float | None = 0.0,
    billing_mode: str = "metered",
) -> tuple[str, str]:
    """Render token/cost labels across metered and subscription backends."""
    if billing_mode == "subscription":
        token_str = f"{total_tokens:,}" if total_tokens is not None else "unknown"
        return token_str, "subscription"
    token_str = f"{(total_tokens or 0):,}"
    cost_str = f"${total_cost:.4f}" if total_cost else "$0"
    return token_str, cost_str


_EVAL_TYPE_HINT: dict[str, str] = {
    "exact_match": "answer must match expected string",
    "numeric":     "numeric within tolerance",
    "contains":    "answer must contain phrases",
    "regex":       "regex pattern match (0 or 1)",
    "code_output": "sandbox runs your code, score from SCORE: line",
    "llm_judge":   "LLM grades against rubric",
    "webhook":     "publisher runs their own eval",
}


def _eval_type_hint(eval_type: str) -> str:
    """Human-readable tail for an eval_type. Empty for unknown types so the
    caller can conditionally skip rendering."""
    return _EVAL_TYPE_HINT.get(eval_type, "")


def _fmt_time_left(iso_str: str) -> str:
    """Turn an ISO timestamp into 'in 3d 5h' / 'in 45m' / 'expired'.
    Returns '-' for missing / unparseable input."""
    if not iso_str:
        return "-"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = dt - datetime.now(timezone.utc)
        secs = int(delta.total_seconds())
        if secs <= 0:
            return "[error]expired[/]"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        days = secs // 86400
        hours = (secs % 86400) // 3600
        if days < 10 and hours:
            return f"{days}d {hours}h"
        return f"{days}d"
    except (ValueError, TypeError):
        return "-"


def _time_ago(iso_str: str) -> str:
    """Convert ISO timestamp to 'Nm ago' / 'Nh ago'."""
    if not iso_str:
        return ""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h ago"
    except Exception:
        return ""


def _truncate_answer(answer: str | None, max_len: int = 70) -> str:
    """Collapse whitespace and truncate an answer for single-line preview."""
    if not answer:
        return ""
    collapsed = re.sub(r"\s+", " ", answer).strip()
    if not collapsed:
        return ""
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[:max_len - 1] + "\u2026"


def _result_style(result: str) -> str:
    """Map result label to semantic theme style."""
    return {
        "COMPLETE": "result.complete",
        "improved": "result.improved",
        "crash": "result.error",
        "error": "result.error",
        "eval error": "result.error",
        "validation error": "result.error",
        "eval timeout": "result.error",
        "rate limited": "result.warning",
        "duplicate": "result.warning",
    }.get(result, "result.neutral")


def _fmt_community(subs: list[dict], my_miner_id: str = "") -> list[str]:
    """Format community leaderboard lines for the mining panel."""
    if not subs:
        return []
    unique = len(set(str(s.get("miner_id", "")) for s in subs))
    lines = [f"[secondary]── Leaderboard ({unique} miners) ──[/]"]
    for i, s in enumerate(subs[:5], 1):
        mid = str(s.get("miner_id", "?"))
        short_id = f"{mid[:4]}..{mid[-4:]}" if len(mid) > 8 else mid
        score = s.get("score")
        score_str = f"{score:.4f}" if score is not None else "    -"
        model = (s.get("llm_model_used") or "?").split("/")[-1][:14]
        ago = _time_ago(s.get("created_at", ""))
        is_me = mid == my_miner_id
        tag = "  [accent]\u2190 you[/]" if is_me else ""
        style = "accent" if is_me else "secondary"
        lines.append(f"  [{style}]#{i}  {short_id}  {score_str}  {model:<14s}  {ago}[/]{tag}")
    return lines


# ── Task List ──────────────────────────────────────────────────────────

def print_task_list(tasks: list[dict]) -> None:
    """Display task list as a DOUBLE_EDGE table with status dots."""
    if not tasks:
        console.print("  [secondary]No tasks found.[/]")
        return

    table = Table(
        title=branded_title("Available Tasks"),
        box=TABLE_BOX,
        border_style=GOLD,
        header_style="header",
    )
    table.add_column("#", justify="right", style="secondary")
    table.add_column("Status", justify="center")
    table.add_column("Pool (USDC)", justify="right")
    table.add_column("Best", justify="right")
    table.add_column("Expires", justify="right", style="secondary")
    table.add_column("Eval", style="secondary")
    table.add_column("Title")

    for i, t in enumerate(tasks, 1):
        status = t.get("status", "?")
        best = f"{t['best_score']:.4f}" if t.get("best_score") is not None else "-"
        pool = _fmt_usdc(t.get("pool_balance", 0))
        table.add_row(
            str(i),
            status_dot(status),
            f"[money]{pool}[/]",
            best,
            _fmt_time_left(t.get("expires_at", "")),
            t.get("eval_type", "?"),
            t.get("title", "?"),
        )

    console.print()
    console.print(table)
    console.print(f"  [success]\u25cf[/] open  [accent]\u25cf[/] completed  [error]\u25cf[/] closed")
    console.print(
        "  [secondary]Eval types:  "
        "exact_match / numeric / contains / regex = text match · "
        "code_output = sandbox runs code · "
        "llm_judge = LLM grades · "
        "webhook = publisher eval[/]"
    )
    console.print()


# ── Task Detail ────────────────────────────────────────────────────────

def print_task_detail(t: dict) -> None:
    """Display a single task's full details in a DOUBLE panel."""
    status = t.get("status", "?")
    direction = t.get("direction", "maximize")
    arrow = "\u2193 lower is better" if direction == "minimize" else "\u2191 higher is better"
    best = f"{t['best_score']:.6f}" if t.get("best_score") is not None else "-"
    baseline = f"{t['baseline_score']:.6f}" if t.get("baseline_score") is not None else "-"
    threshold = t.get("completion_threshold", "?")

    kv = Table(box=None, show_header=False, padding=(0, 2))
    kv.add_column("Key", style="secondary")
    kv.add_column("Value")

    kv.add_row("ID", f"[secondary]{t.get('id', '?')}[/]")
    kv.add_row("Status", status_dot(status) + f" {status}")
    eval_type = t.get("eval_type", "?")
    eval_hint = _eval_type_hint(eval_type)
    eval_value = f"{eval_type}  [secondary]({arrow}"
    eval_value += f"  ·  {eval_hint})[/]" if eval_hint else ")[/]"
    kv.add_row("Eval", eval_value)
    kv.add_row(
        "Threshold",
        f"{threshold}  [secondary](beat this AND community best to earn)[/]",
    )
    kv.add_row("Pool", f"[money]{_fmt_usdc(t.get('pool_balance', 0))}[/]")
    pct = t.get("completion_reward_pct", 50)
    bonus = (t.get("pool_balance", 0) * pct) // 100
    kv.add_row(
        "Completion Bonus",
        f"[money]{_fmt_usdc(bonus)}[/]  [secondary]({pct}% of pool, paid to first miner to cross threshold)[/]",
    )
    kv.add_row("Community Best", best)
    kv.add_row("Baseline", f"{baseline}  [secondary](starting score)[/]")
    kv.add_row("Expires in", _fmt_time_left(t.get("expires_at", "")))

    panel = Panel(
        kv,
        title=branded_title(t.get("title", "?")),
        box=PRIMARY_BOX,
        border_style=GOLD,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)

    desc = t.get("description", "")
    if desc:
        console.print(f"\n[brand]Description[/]\n")
        for line in desc.strip().splitlines():
            console.print(f"  {line}")

    console.print()


# ── Rounds formatting ──────────────────────────────────────────────────

def fmt_rounds_header() -> str:
    """Header row for the rounds list."""
    return f"  [secondary]{'Round':<9} {'Score':>10}  {'Result':<14} {'Earned'}[/]"


def fmt_round(round_num: int, score: float | None, result: str, earned: int) -> str:
    """Format one round line as Rich markup."""
    label = f"Round {round_num}"
    score_str = f"{score:.6f}" if score is not None else "      -"
    earned_tag = f"  +{_fmt_usdc(earned)}" if earned else ""
    style = _result_style(result)
    return f"  [{style}]{label:<9} {score_str}  {result}{earned_tag}[/]"


# ── Mining Summary ─────────────────────────────────────────────────────

def print_mining_summary(rounds_data: list[dict], best_score: float | None,
                         total_earned: int, round_count: int,
                         total_tokens: int | None = 0, total_cost: float | None = 0.0,
                         billing_mode: str = "metered") -> None:
    """Rich Table summary at end of mining."""
    table = Table(
        title=branded_title("Mining Summary"),
        box=TABLE_BOX,
        border_style=GOLD,
        header_style="header",
    )
    table.add_column("Round", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Result")
    table.add_column("Earned", justify="right")

    for r in rounds_data:
        score_str = f"{r['score']:.6f}" if r.get("score") is not None else "error"
        earned_str = f"+{_fmt_usdc(r['earned'])}" if r.get("earned") else "-"
        style = _result_style(r["result"])
        table.add_row(str(r["round"]), score_str, f"[{style}]{r['result']}[/]", earned_str)

    console.print()
    console.print(table)
    best_str = f"{best_score:.6f}" if best_score is not None else "N/A"
    token_str, cost_str = _format_usage_summary(total_tokens, total_cost, billing_mode)
    console.print(f"  Best: {best_str}  Earned: [money]+{_fmt_usdc(total_earned)}[/]  Tokens: {token_str}  Cost: [warning]{cost_str}[/]  Rounds: {round_count}")
    console.print()


# ── Mining Panel (live) ────────────────────────────────────────────────

def build_mining_panel(
    task_title: str,
    model: str,
    pool: int,
    threshold: float,
    best_score: float | None,
    total_earned: int,
    round_count: int,
    status: str,
    show_details: bool,
    last_detail: dict | None,
    rounds: list[dict] | None = None,
    detail_nav: tuple[int, int] | None = None,
    total_tokens: int | None = 0,
    total_cost: float | None = 0.0,
    billing_mode: str = "metered",
    community_subs: list[dict] | None = None,
    community_total: int = 0,
    my_miner_id: str = "",
    max_rounds: int = 0,
    budget: float = 0,
    timeout: int = 0,
    completion_reward_pct: int = 50,
) -> Panel:
    """Compact mining status panel with DOUBLE box."""
    model_short = model.split("/")[-1] if "/" in model else model
    best_str = f"{best_score:.6f}" if best_score is not None else "-"
    token_str, cost_str = _format_usage_summary(total_tokens, total_cost, billing_mode)

    lines = [
        f"Model: [accent]{model_short}[/]  Pool: [money]{_fmt_usdc(pool)}[/]  Reward: [money]{_fmt_usdc((pool * completion_reward_pct) // 100)}[/]  Threshold: {threshold}",
        f"Best:  {best_str}  Earned: [money]{_fmt_usdc(total_earned)}[/]  Rounds: {round_count}",
        f"Tokens: {token_str}  Cost: [warning]{cost_str}[/]",
    ]

    rounds_str = "\u221e" if max_rounds == 0 else str(max_rounds)
    budget_str = "n/a" if billing_mode != "metered" else ("\u221e" if budget == 0 else f"${budget:.2f}")
    timeout_str = "\u221e" if timeout == 0 else f"{timeout}s"
    lines.append(f"Rounds: {rounds_str}  Budget: {budget_str}  Timeout: {timeout_str}")

    if rounds:
        lines.append("")
        lines.append(fmt_rounds_header())
        for r in rounds[-5:]:
            lines.append(fmt_round(r["round"], r["score"], r["result"], r["earned"]))

    if community_subs and not show_details:
        lines.append("")
        lines.extend(_fmt_community(community_subs, my_miner_id))

    if status:
        lines.append(status)

    if show_details and last_detail:
        nav_str = ""
        if detail_nav:
            nav_str = f"  [accent]Round {detail_nav[0]}/{detail_nav[1]}[/]"
        lines.append("")
        lines.append(f"[brand]\u2500\u2500 Details{nav_str} \u2500\u2500[/]")
        result = last_detail.get("result", "")
        rstyle = _result_style(result)
        score_str = f"{last_detail['score']:.6f}" if last_detail.get("score") is not None else "-"
        earned = last_detail.get("earned", 0)
        earned_tag = f"  [money]+{_fmt_usdc(earned)}[/]" if earned else ""
        lines.append(f"Result: [{rstyle}]{result}[/]  Score: {score_str}{earned_tag}")
        if last_detail.get("error"):
            lines.append(f"Error:  [error]{last_detail['error'][:200]}[/]")
        details = last_detail.get("eval_details") or {}
        if details.get("stdout"):
            stdout_text = str(details["stdout"])[:300].replace("\n", "\n        ")
            lines.append(f"Output: [secondary]{stdout_text}[/]")
        if details.get("stderr"):
            stderr_text = str(details["stderr"])[:200].replace("\n", "\n        ")
            lines.append(f"Stderr: [error]{stderr_text}[/]")
        if last_detail.get("thinking"):
            thinking_preview = last_detail["thinking"][:200].replace("\n", "\\n")
            lines.append(f"Think:  [secondary]{thinking_preview}[/]")
        if last_detail.get("answer"):
            preview = last_detail["answer"][:200].replace("\n", "\\n")
            lines.append(f"Answer: [secondary]{preview}[/]")

    if show_details:
        hint = "ctrl+c stop \u00b7 \u2190 \u2192 browse \u00b7 ctrl+o close"
    else:
        hint = "ctrl+c stop \u00b7 ctrl+o details"
    lines.append(f"\n[secondary]{hint}[/]")

    return Panel(
        "\n".join(lines),
        title=branded_title(task_title),
        box=PRIMARY_BOX,
        border_style=GOLD,
        padding=(1, 2),
    )


def _progress_bar(progress: float, width: int = 8) -> str:
    """Render a Unicode progress bar."""
    filled = round(progress * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


# ── Network Pulse ──────────────────────────────────────────────────────
#
# Mirrors the webapp /network page: hero stats, recent activity, 7-day
# submissions chart, top miners, top 5 hot tasks. Each section accepts
# `None` to mean "API failed" and renders a graceful fallback so a single
# down endpoint doesn't black out the whole dashboard.

# Activity event type → (verb label, Rich style).
_ACTIVITY_VERBS = {
    "improvement":          ("improved",     "result.improved"),
    "completion":           ("completed",    "result.complete"),
    "task_fund":            ("funded",       "accent"),
    "task_refund":          ("refunded",     "secondary"),
    "deposit":              ("deposited",    "money"),
    "withdrawal_requested": ("withdrew",     "secondary"),
}


def _short_addr(addr: str | None) -> str:
    if not addr:
        return "—"
    return f"{addr[:6]}..{addr[-4:]}"


def _fill_missing_days(data: list[dict] | None, days: int) -> list[tuple[str, int]]:
    """Pad the daily-counts payload to `days` entries ending today, inserting
    zero-count days for missing ones. Server omits empty days."""
    from datetime import datetime, timezone, timedelta
    by_day = {row.get("day"): int(row.get("count", 0)) for row in (data or [])}
    today = datetime.now(timezone.utc).date()
    out: list[tuple[str, int]] = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        out.append((key, by_day.get(key, 0)))
    return out


def _render_hero(stats: dict | None, network: dict | None) -> Panel:
    """Hero strip with 4 non-overlapping-with-Home stats."""
    if stats is None and network is None:
        return Panel(
            "[error]stats unavailable[/]",
            title=branded_title("Network Pulse"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )
    s = stats or {}
    n = network or {}

    grid = Table(box=None, show_header=False, padding=(0, 3))
    for _ in range(4):
        grid.add_column(justify="center")

    grid.add_row(
        "[secondary]24H REWARDS[/]",
        "[secondary]24H NEW POOLS[/]",
        "[secondary]MINERS 24H[/]",
        "[secondary]SUBS 24H[/]",
    )
    grid.add_row(
        f"[money.bold]{_fmt_usdc(s.get('rewards_paid_24h', 0))}[/]",
        f"[money.bold]{_fmt_usdc(s.get('new_pools_24h', 0))}[/]",
        f"[brand]{n.get('active_miners_24h', 0)}[/]",
        f"[brand]{s.get('submissions_24h', 0)}[/]",
    )
    return Panel(
        grid,
        title=branded_title("Network Pulse"),
        box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
    )


def _render_activity(events: list | None) -> Panel:
    if events is None:
        return Panel(
            "[secondary]activity feed unavailable[/]",
            title=branded_title("Recent Activity"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )
    if not events:
        return Panel(
            "[secondary]No recent events.[/]",
            title=branded_title("Recent Activity"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("when", width=6, style="secondary")
    table.add_column("actor", width=14)
    table.add_column("verb", width=12)
    table.add_column("target")
    table.add_column("amt", justify="right", width=10)

    for ev in events[:10]:
        when = _time_ago(ev.get("created_at", "")) or "—"
        actor = _short_addr(ev.get("actor_address"))
        verb_label, verb_style = _ACTIVITY_VERBS.get(
            ev.get("type"), (ev.get("type", "—"), "secondary"),
        )

        title = ev.get("task_title") or "—"
        if len(title) > 26:
            title = title[:23] + "…"
        score = ev.get("new_score")
        target = title + (f" → {score:.3f}" if score is not None else "")

        amount_cents = ev.get("amount_cents") or 0
        if amount_cents:
            sign = "+" if amount_cents > 0 else "-"
            amt = f"[money]{sign}{_fmt_usdc(abs(amount_cents))}[/]"
        else:
            amt = "—"

        table.add_row(
            when,
            f"[address]{actor}[/]",
            f"[{verb_style}]{verb_label}[/]",
            target,
            amt,
        )

    return Panel(
        table,
        title=branded_title("Recent Activity"),
        box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
    )


def _render_sparkline(daily: list | None, days: int = 7,
                       width: int = 56, rows: int = 5) -> Panel:
    """Multi-line ASCII line chart with Y-axis ticks + per-point value labels.

    Width is in monospace columns inside the panel. `rows` controls vertical
    resolution (so a value of `max` is at row 0 and `0` is at row rows-1).
    Days with zero count are still plotted on the baseline so the chart
    spans the whole 7-day window even on quiet weeks.
    """
    if daily is None:
        return Panel(
            "[secondary]chart unavailable[/]",
            title=branded_title("Submissions · 7d"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )
    filled = _fill_missing_days(daily, days)
    counts = [c for _, c in filled]
    max_v = max(counts) if counts else 0

    if max_v == 0:
        body = "[secondary]No submissions in the last 7 days.[/]"
        return Panel(
            body, title=branded_title("Submissions · 7d"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )

    n = len(filled)
    cols = [round(i * (width - 1) / max(n - 1, 1)) for i in range(n)]
    grid: list[list[str]] = [[" "] * width for _ in range(rows)]
    for i, (_, v) in enumerate(filled):
        col = cols[i]
        if v == 0:
            row = rows - 1
        else:
            row = rows - 1 - round((v / max_v) * (rows - 1))
        grid[row][col] = "●"

    label_w = 3
    lines: list[str] = []
    for r in range(rows):
        if r == 0:
            tick = f"{max_v:>{label_w}}"
        elif r == rows - 1:
            tick = f"{0:>{label_w}}"
        elif r == rows // 2:
            tick = f"{max_v // 2:>{label_w}}"
        else:
            tick = " " * label_w
        body_chars = "".join(grid[r])
        # Tick separator: solid line on max/mid/0 rows, dotted otherwise
        sep = "┤" if tick.strip() else "┊"
        lines.append(f"  [secondary]{tick}[/] {sep} {body_chars}")

    # Bottom rule + X-axis date labels (start, end)
    lines.append(f"  {' ' * label_w} └{'─' * (width + 1)}")
    first = filled[0][0][5:]   # MM-DD
    last = filled[-1][0][5:]
    pad = max(width + 2 - len(first) - len(last), 1)
    lines.append(
        f"  [secondary]{' ' * label_w}  {first}{' ' * pad}{last}[/]",
    )

    body_text = "\n".join(lines)
    return Panel(
        body_text,
        title=branded_title("Submissions · 7d"),
        box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
    )


def _render_leaderboard(rows_data: list | None, window: str = "7d") -> Panel:
    if rows_data is None:
        return Panel(
            "[secondary]leaderboard unavailable[/]",
            title=branded_title(f"Top Miners · {window}"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )
    if not rows_data:
        return Panel(
            "[secondary]No earnings yet in this window.[/]",
            title=branded_title(f"Top Miners · {window}"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )

    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("rank", width=4)
    table.add_column("addr", width=18)
    table.add_column("earned", justify="right")
    table.add_column("rewards", justify="right", style="secondary")

    for r in rows_data[:5]:
        table.add_row(
            f"[accent]#{r.get('rank', '?')}[/]",
            f"[address]{_short_addr(r.get('address'))}[/]",
            f"[money]{_fmt_usdc(r.get('earned_cents', 0))}[/]",
            f"{r.get('txn_count', 0)} reward",
        )
    return Panel(
        table,
        title=branded_title(f"Top Miners · {window}"),
        box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
    )


def _render_hot_tasks(network: dict | None) -> Panel:
    """Top 5 open tasks by submissions/1h. Uses the same /api/network payload
    that fed the old print_network table — we just slice + sort."""
    if network is None:
        return Panel(
            "[secondary]tasks unavailable[/]",
            title=branded_title("Top 5 Hot Tasks"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )

    tasks = network.get("tasks", []) or []
    # Drop expired-but-not-yet-flipped tasks so the heat ranking is meaningful
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    def _not_expired(t: dict) -> bool:
        iso = t.get("expires_at")
        if not iso:
            return True
        try:
            d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return d > now
        except (ValueError, TypeError):
            return True
    open_tasks = [t for t in tasks if _not_expired(t)]
    sorted_tasks = sorted(open_tasks,
                          key=lambda t: t.get("submissions_1h", 0),
                          reverse=True)[:5]

    if not sorted_tasks:
        return Panel(
            "[secondary]No active tasks.[/]",
            title=branded_title("Top 5 Hot Tasks"),
            box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
        )

    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("rank", width=4)
    table.add_column("title")
    table.add_column("subs", justify="right", style="secondary")
    table.add_column("expires", justify="right")
    table.add_column("pool", justify="right")

    for i, t in enumerate(sorted_tasks, 1):
        title = t.get("title", "?")
        if len(title) > 30:
            title = title[:27] + "…"
        table.add_row(
            f"[accent]#{i}[/]",
            f"[brand]{title}[/]",
            f"{t.get('submissions_1h', 0)}/1h",
            _fmt_time_left(t.get("expires_at", "")),
            f"[money]{_fmt_usdc(t.get('pool_balance', 0))}[/]",
        )

    return Panel(
        table,
        title=branded_title("Top 5 Hot Tasks"),
        box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2),
    )


def print_network_pulse(
    *,
    stats: dict | None,
    network: dict | None,
    activity: list | None,
    daily: list | None,
    miners: list | None,
    leaderboard_window: str = "7d",
) -> None:
    """Render the full Network Pulse dashboard.

    Each kwarg is independent: passing None for any of them swaps in a
    'unavailable' placeholder so a single failed endpoint doesn't black
    out the whole page (Rich `safe_print` style)."""
    console.print()
    console.print(_render_hero(stats, network))
    console.print()
    console.print(_render_activity(activity))
    console.print()
    console.print(_render_sparkline(daily))
    console.print()
    console.print(_render_leaderboard(miners, window=leaderboard_window))
    console.print()
    console.print(_render_hot_tasks(network))
    console.print()


def print_network(data: dict) -> None:
    """Backwards-compatible single-payload entry point.

    Kept for `axon.preview` and any external callers that pass the raw
    `/api/network` response. The real dashboard lives in
    `print_network_pulse`; this thin wrapper hands off with the other
    inputs missing — the renderers will gracefully degrade."""
    print_network_pulse(
        stats=None,
        network=data,
        activity=None,
        daily=None,
        miners=None,
    )


# ── Stats ──────────────────────────────────────────────────────────────

def print_stats(user: dict, breakdown: dict, improvements: int) -> None:
    """Mining statistics display with DOUBLE panel."""
    pool_rewards = breakdown.get("pool_reward", 0)
    completion_rewards = breakdown.get("completion_reward", 0)

    kv = Table(box=None, show_header=False, padding=(0, 2))
    kv.add_column("Key", style="secondary")
    kv.add_column("Value")

    kv.add_row("Wallet", f"[address]{user.get('address', '?')}[/]")
    kv.add_row("Balance", f"[money.bold]{_fmt_usdc(user.get('balance', 0))}[/]")
    kv.add_row("", "")
    kv.add_row("Income", "")
    kv.add_row("  Pool rewards", f"[money]+{_fmt_usdc(pool_rewards)}[/]")
    if completion_rewards:
        kv.add_row("  Completion reward", f"[money]+{_fmt_usdc(completion_rewards)}[/]")
    kv.add_row("", "")
    kv.add_row("Improvements", str(improvements))

    panel = Panel(kv, title=branded_title("Mining Stats"), box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2))
    console.print()
    console.print(panel)
    console.print()
