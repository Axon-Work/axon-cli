"""Rich display helpers — all CLI formatting lives here."""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_tasks(tasks: list[dict], title: str = "Open Tasks"):
    """Rich Table for task listing."""
    table = Table(title=f"ψ {title}", title_style="bold gold1", border_style="dim")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title")
    table.add_column("Eval", style="dim")
    table.add_column("Best", justify="right")
    table.add_column("Pool", justify="right", style="green")

    for t in tasks:
        tid = t["id"][:8]
        best = f"{t['best_score']:.2f}" if t.get("best_score") is not None else "-"
        pool = f"{t['pool_balance']} $AXN"
        table.add_row(tid, t["title"][:50], t.get("eval_type", ""), best, pool)

    console.print()
    console.print(table)
    console.print()


def print_task_detail(t: dict):
    """Structured task detail view."""
    console.print(f"\n  [bold gold1]ψ {t['title']}[/]\n")
    console.print(f"  ID         [cyan]{t['id']}[/]")
    console.print(f"  Eval       {t['eval_type']} ({t['direction']})")
    console.print(f"  Status     {t['status']}")
    console.print(f"  Threshold  {t['completion_threshold']}")
    best = f"{t['best_score']:.4f}" if t.get("best_score") is not None else "-"
    console.print(f"  Best       {best}")
    console.print(f"  Pool       [green]{t['pool_balance']} $AXN[/]")
    if t.get("description"):
        console.print(f"\n  [bold]Description[/]\n  {t['description']}")
    console.print()


def fmt_round(round_num: int, score: float | None, result: str, earned: int) -> str:
    """Format one round line as Rich markup."""
    score_str = f"{score:.6f}" if score is not None else "      -"
    if result == "crash":
        return f"  [red]R{round_num:>2}  {score_str}  crash[/]"
    if result in ("error", "eval error"):
        return f"  [red]R{round_num:>2}  {score_str}  {result}[/]"
    if result == "rate limited":
        return f"  [yellow]R{round_num:>2}  {score_str}  rate limited[/]"
    if result == "duplicate":
        return f"  [yellow]R{round_num:>2}  {score_str}  duplicate[/]"
    if result == "COMPLETE":
        tag = f"  +{earned} $AXN" if earned else ""
        return f"  [bold green]R{round_num:>2}  {score_str}  COMPLETE{tag}[/]"
    if result == "improved":
        tag = f"  +{earned} $AXN" if earned else ""
        return f"  [green]R{round_num:>2}  {score_str}  improved{tag}[/]"
    return f"  [dim]R{round_num:>2}  {score_str}  no change[/]"


def print_mining_summary(rounds_data: list[dict], best_score: float | None,
                         total_earned: int, round_count: int):
    """Rich Table summary at end of mining."""
    table = Table(title="ψ Mining Summary", title_style="bold gold1", border_style="dim")
    table.add_column("Round", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Result")
    table.add_column("Earned", justify="right")

    for r in rounds_data:
        score_str = f"{r['score']:.6f}" if r.get("score") is not None else "error"
        earned_str = f"+{r['earned']}" if r.get("earned") else "-"
        table.add_row(str(r["round"]), score_str, r["result"], earned_str)

    console.print()
    console.print(table)
    best_str = f"{best_score:.6f}" if best_score is not None else "N/A"
    console.print(f"  Best:    {best_str}")
    console.print(f"  Earned:  [green]{total_earned} $AXN[/]")
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
) -> Panel:
    """Compact mining status panel. All info lives inside the panel."""
    model_short = model.split("/")[-1] if "/" in model else model
    best_str = f"{best_score:.6f}" if best_score is not None else "-"

    lines = [
        f"Model: [cyan]{model_short}[/]  Pool: [green]{pool} $AXN[/]  Threshold: {threshold}",
        f"Best:  {best_str}  Earned: [green]{total_earned} $AXN[/]  Rounds: {round_count}",
    ]

    # Recent rounds history (last 5)
    if rounds:
        lines.append("")
        for r in rounds[-5:]:
            lines.append(fmt_round(r["round"], r["score"], r["result"], r["earned"]))

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
        earned_tag = f"  [green]+{earned} $AXN[/]" if earned else ""
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


def print_stats(user: dict, earned: int, burned: int, improvements: int):
    """Mining statistics display."""
    console.print(f"\n[bold gold1]ψ Mining Stats[/]\n")
    console.print(f"  Wallet      [cyan]{user.get('address', '?')}[/]")
    console.print(f"  Balance     [green]{user.get('balance', 0):,} $AXN[/]")
    console.print(f"  Earned      [green]{earned:,} $AXN[/]")
    console.print(f"  Burned      [red]{burned:,} $AXN[/]")
    console.print(f"  Improvements {improvements}")
    console.print()
