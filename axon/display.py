"""Rich display helpers — all CLI formatting lives here."""
import re

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_banner():
    console.print()
    console.print("  [bold gold1]ψ  A X O N[/]")
    console.print("  [dim]─────────────────[/]")
    console.print("  [dim]World Intelligence[/]")
    console.print("  [dim]Proof of Useful Work[/]")
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


def _fmt_community(subs: list[dict], my_miner_id: str = "") -> list[str]:
    """Format community leaderboard lines for the mining panel."""
    if not subs:
        return []
    unique = len(set(str(s.get("miner_id", "")) for s in subs))
    lines = [f"[bold dim]── Leaderboard ({unique} miners) ──[/]"]
    for i, s in enumerate(subs[:5], 1):
        mid = str(s.get("miner_id", "?"))
        short_id = f"{mid[:4]}..{mid[-4:]}" if len(mid) > 8 else mid
        score = s.get("score")
        score_str = f"{score:.4f}" if score is not None else "    -"
        model = (s.get("llm_model_used") or "?").split("/")[-1][:14]
        ago = _time_ago(s.get("created_at", ""))
        is_me = mid == my_miner_id
        tag = "  [cyan]← you[/]" if is_me else ""
        style = "cyan" if is_me else "dim"
        lines.append(f"  [{style}]#{i}  {short_id}  {score_str}  {model:<14s}  {ago}[/]{tag}")
        # Answer preview for non-self entries
        if not is_me:
            preview = _truncate_answer(s.get("answer"))
            if preview:
                lines.append(f"       [dim italic]\u201c{escape(preview)}\u201d[/]")
    return lines


def print_task_list(tasks: list[dict]):
    """Display task list as a table."""
    if not tasks:
        console.print("  [dim]No tasks found.[/]")
        return

    table = Table(title="ψ Available Tasks", title_style="bold gold1", border_style="dim")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Pool (USDC)", justify="right")
    table.add_column("Best", justify="right")
    table.add_column("Eval", style="dim")
    table.add_column("Title")

    for i, t in enumerate(tasks, 1):
        status_style = {"open": "green", "completed": "blue", "closed": "red"}.get(t.get("status", ""), "dim")
        best = f"{t['best_score']:.4f}" if t.get("best_score") is not None else "-"
        pool = _fmt_usdc(t.get("pool_balance", 0))
        table.add_row(
            str(i),
            f"[{status_style}]{t.get('status', '?')}[/]",
            f"[green]{pool}[/]",
            best,
            t.get("eval_type", "?"),
            t.get("title", "?"),
        )

    console.print()
    console.print(table)
    console.print()


def print_task_detail(t: dict):
    """Display a single task's full details."""
    status = t.get("status", "?")
    status_style = {"open": "green", "completed": "blue", "closed": "red"}.get(status, "dim")
    direction = t.get("direction", "maximize")
    arrow = "↓ lower is better" if direction == "minimize" else "↑ higher is better"
    best = f"{t['best_score']:.6f}" if t.get("best_score") is not None else "-"
    baseline = f"{t['baseline_score']:.6f}" if t.get("baseline_score") is not None else "-"
    threshold = t.get("completion_threshold", "?")

    console.print(f"\n[bold gold1]ψ {t.get('title', '?')}[/]\n")
    console.print(f"  ID          [dim]{t.get('id', '?')}[/]")
    console.print(f"  Status      [{status_style}]{status}[/]")
    console.print(f"  Eval        {t.get('eval_type', '?')}  [dim]({arrow})[/]")
    console.print(f"  Threshold   {threshold}")
    console.print(f"  Pool        [green]{_fmt_usdc(t.get('pool_balance', 0))}[/]")
    console.print(f"  Best Score  {best}")
    console.print(f"  Baseline    {baseline}")

    desc = t.get("description", "")
    if desc:
        console.print(f"\n[bold]Description[/]\n")
        for line in desc.strip().splitlines():
            console.print(f"  {line}")

    console.print()


def fmt_rounds_header() -> str:
    """Header row for the rounds list."""
    return f"  [bold dim]{'Round':<9} {'Score':>10}  {'Result':<14} {'Earned'}[/]"


def fmt_round(round_num: int, score: float | None, result: str, earned: int) -> str:
    """Format one round line as Rich markup."""
    label = f"Round {round_num}"
    score_str = f"{score:.6f}" if score is not None else "      -"
    earned_tag = f"  +{_fmt_usdc(earned)}" if earned else ""
    if result == "crash":
        return f"  [red]{label:<9} {score_str}  crash[/]"
    if result in ("error", "eval error"):
        return f"  [red]{label:<9} {score_str}  {result}[/]"
    if result == "rate limited":
        return f"  [yellow]{label:<9} {score_str}  rate limited[/]"
    if result == "duplicate":
        return f"  [yellow]{label:<9} {score_str}  duplicate[/]"
    if result == "COMPLETE":
        return f"  [bold green]{label:<9} {score_str}  COMPLETE{earned_tag}[/]"
    if result == "improved":
        return f"  [green]{label:<9} {score_str}  improved{earned_tag}[/]"
    return f"  [dim]{label:<9} {score_str}  no change[/]"


def print_mining_summary(rounds_data: list[dict], best_score: float | None,
                         total_earned: int, round_count: int,
                         total_tokens: int | None = 0, total_cost: float | None = 0.0,
                         billing_mode: str = "metered"):
    """Rich Table summary at end of mining."""
    table = Table(title="ψ Mining Summary", title_style="bold gold1", border_style="dim")
    table.add_column("Round", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Result")
    table.add_column("Earned", justify="right")

    for r in rounds_data:
        score_str = f"{r['score']:.6f}" if r.get("score") is not None else "error"
        earned_str = f"+{_fmt_usdc(r['earned'])}" if r.get("earned") else "-"
        table.add_row(str(r["round"]), score_str, r["result"], earned_str)

    console.print()
    console.print(table)
    best_str = f"{best_score:.6f}" if best_score is not None else "N/A"
    token_str, cost_str = _format_usage_summary(total_tokens, total_cost, billing_mode)
    console.print(f"  Best:    {best_str}")
    console.print(f"  Earned:  [green]{_fmt_usdc(total_earned)}[/]")
    console.print(f"  Tokens:  {token_str}  Cost: [yellow]{cost_str}[/]")
    console.print(f"  Rounds:  {round_count}")
    console.print()


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
) -> Panel:
    """Compact mining status panel. All info lives inside the panel."""
    model_short = model.split("/")[-1] if "/" in model else model
    best_str = f"{best_score:.6f}" if best_score is not None else "-"
    token_str, cost_str = _format_usage_summary(total_tokens, total_cost, billing_mode)

    lines = [
        f"Model: [cyan]{model_short}[/]  Pool: [green]{_fmt_usdc(pool)}[/]  Threshold: {threshold}",
        f"Best:  {best_str}  Earned: [green]{_fmt_usdc(total_earned)}[/]  Rounds: {round_count}",
        f"Tokens: {token_str}  Cost: [yellow]{cost_str}[/]",
    ]

    # Recent rounds history (last 5)
    if rounds:
        lines.append("")
        lines.append(fmt_rounds_header())
        for r in rounds[-5:]:
            lines.append(fmt_round(r["round"], r["score"], r["result"], r["earned"]))

    # Community leaderboard
    if community_subs:
        lines.append("")
        lines.extend(_fmt_community(community_subs, my_miner_id))

    if status:
        lines.append(status)

    # ctrl+o expands full details; left/right navigates rounds
    if show_details and last_detail:
        nav_str = ""
        if detail_nav:
            nav_str = f"  [bold cyan]Round {detail_nav[0]}/{detail_nav[1]}[/]"
        lines.append("")
        lines.append(f"[bold]── Details{nav_str} ──[/]")
        result = last_detail.get("result", "")
        result_styles = {"COMPLETE": "bold green", "improved": "green",
                         "eval error": "red", "crash": "red", "error": "red",
                         "rate limited": "yellow", "duplicate": "yellow", "no change": "dim"}
        rstyle = result_styles.get(result, "dim")
        score_str = f"{last_detail['score']:.6f}" if last_detail.get("score") is not None else "-"
        earned = last_detail.get("earned", 0)
        earned_tag = f"  [green]+{_fmt_usdc(earned)}[/]" if earned else ""
        lines.append(f"Result: [{rstyle}]{result}[/]  Score: {score_str}{earned_tag}")
        if last_detail.get("error"):
            lines.append(f"Error:  [red]{last_detail['error'][:200]}[/]")
        details = last_detail.get("eval_details") or {}
        if details.get("stdout"):
            stdout_text = str(details["stdout"])[:300].replace("\n", "\n        ")
            lines.append(f"Output: [dim]{stdout_text}[/]")
        if details.get("stderr"):
            stderr_text = str(details["stderr"])[:200].replace("\n", "\n        ")
            lines.append(f"Stderr: [red]{stderr_text}[/]")
        if last_detail.get("thinking"):
            thinking_preview = last_detail["thinking"][:200].replace("\n", "\\n")
            lines.append(f"Think:  [dim]{thinking_preview}[/]")
        if last_detail.get("answer"):
            preview = last_detail["answer"][:200].replace("\n", "\\n")
            lines.append(f"Answer: [dim]{preview}[/]")

    if show_details:
        hint = "ctrl+c stop · ← → browse · ctrl+o close"
    else:
        hint = "ctrl+c stop · ctrl+o details"
    lines.append(f"\n[dim]{hint}[/]")

    return Panel(
        "\n".join(lines),
        title=f"[bold gold1]ψ {task_title}[/]",
        border_style="gold1",
        padding=(1, 2),
    )


def _progress_bar(progress: float, width: int = 8) -> str:
    """Render a Unicode progress bar like ███░░░░░."""
    filled = round(progress * width)
    return "█" * filled + "░" * (width - filled)


def print_network(data: dict):
    """Display global network overview + per-task competition table."""
    console.print(f"\n[bold gold1]ψ Network Overview[/]\n")
    console.print(f"  Active miners (24h)   {data.get('active_miners_24h', 0)}")
    console.print(f"  Submissions/hr        {data.get('submissions_1h', 0)}")
    console.print(f"  Open reward pool      [green]{_fmt_usdc(data.get('total_open_pool', 0))}[/]")
    console.print(f"  Total rewards paid    [green]{_fmt_usdc(data.get('total_rewards_paid', 0))}[/]")

    tasks = data.get("tasks", [])
    if not tasks:
        console.print("\n  [dim]No open tasks.[/]\n")
        return

    table = Table(title="Open Task Competition", title_style="bold", border_style="dim")
    table.add_column("Title", max_width=26)
    table.add_column("Pool", justify="right")
    table.add_column("Thrs", justify="right")
    table.add_column("Best", justify="right")
    table.add_column("Progress")
    table.add_column("Miners", justify="right")
    table.add_column("Subs/hr", justify="right")

    for t in tasks:
        pool = _fmt_usdc(t.get("pool_balance", 0))
        threshold = f"{t.get('completion_threshold', 0):.2f}"
        best = f"{t['best_score']:.4f}" if t.get("best_score") is not None else "-"
        progress = t.get("progress", 0.0)
        bar = _progress_bar(progress)
        pct = f"{progress * 100:.0f}%"
        table.add_row(
            t.get("title", "?"),
            f"[green]{pool}[/]",
            threshold,
            best,
            f"{bar} {pct:>4s}",
            str(t.get("active_miners_24h", 0)),
            str(t.get("submissions_1h", 0)),
        )

    console.print()
    console.print(table)
    console.print()


def print_stats(user: dict, breakdown: dict, improvements: int):
    """Mining statistics display with transaction breakdown."""
    pool_rewards = breakdown.get("pool_reward", 0)
    completion_rewards = breakdown.get("completion_reward", 0)

    console.print(f"\n[bold gold1]ψ Mining Stats[/]\n")
    console.print(f"  Wallet        [cyan]{user.get('address', '?')}[/]")
    console.print(f"  Balance       [bold green]{_fmt_usdc(user.get('balance', 0))}[/]")
    console.print()
    console.print(f"  [bold]Income[/]")
    console.print(f"  Pool rewards     [green]+{_fmt_usdc(pool_rewards)}[/]")
    if completion_rewards:
        console.print(f"  Completion bonus [green]+{_fmt_usdc(completion_rewards)}[/]")
    console.print()
    console.print(f"  Improvements  {improvements}")
    console.print()
