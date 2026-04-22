"""Preview all CLI components with mock data.  Run: python -m axon.preview"""
from axon.theme import console, branded_title
from axon.display import (
    print_banner, print_task_list, print_task_detail,
    print_mining_summary, build_mining_panel,
    print_network, print_stats,
)


def main() -> None:
    console.print("\n[brand]── CRT Theme Preview ──[/]\n")

    # Banner
    print_banner()

    # Task list
    print_task_list([
        {"status": "open", "title": "Summarize Wikipedia", "pool_balance": 50000,
         "best_score": 0.8712, "eval_type": "rouge"},
        {"status": "completed", "title": "Translate EN→FR", "pool_balance": 0,
         "best_score": 0.9510, "eval_type": "bleu"},
        {"status": "closed", "title": "Code Generation", "pool_balance": 0,
         "best_score": 0.6200, "eval_type": "pass@1"},
    ])

    # Task detail
    print_task_detail({
        "id": "abc-123-def",
        "title": "Summarize Wikipedia",
        "status": "open",
        "eval_type": "rouge",
        "direction": "maximize",
        "completion_threshold": 0.95,
        "pool_balance": 50000,
        "best_score": 0.8712,
        "baseline_score": 0.5000,
        "description": "Given a Wikipedia article, produce a concise summary.\n"
                       "The summary should capture all key facts in under 200 words.",
    })

    # Mining summary
    print_mining_summary(
        [
            {"round": 1, "score": 0.710000, "result": "improved", "earned": 200},
            {"round": 2, "score": 0.750000, "result": "improved", "earned": 150},
            {"round": 3, "score": None, "result": "rate limited", "earned": 0},
            {"round": 4, "score": 0.871200, "result": "improved", "earned": 300},
            {"round": 5, "score": 0.950000, "result": "COMPLETE", "earned": 5000},
        ],
        best_score=0.950000,
        total_earned=5650,
        round_count=5,
        total_tokens=12500,
        total_cost=0.0372,
    )

    # Mining panel (live)
    panel = build_mining_panel(
        task_title="Summarize Wikipedia",
        model="anthropic/claude-sonnet-4-20250514",
        pool=50000,
        threshold=0.95,
        best_score=0.8712,
        total_earned=650,
        round_count=4,
        status="[secondary]► Round 5  calling claude-sonnet-4...[/]",
        show_details=False,
        last_detail=None,
        rounds=[
            {"round": 1, "score": 0.71, "result": "improved", "earned": 200},
            {"round": 2, "score": 0.75, "result": "improved", "earned": 150},
            {"round": 3, "score": None, "result": "rate limited", "earned": 0},
            {"round": 4, "score": 0.8712, "result": "improved", "earned": 300},
        ],
    )
    console.print(panel)

    # Network
    print_network({
        "active_miners_24h": 42,
        "submissions_1h": 128,
        "total_open_pool": 250000,
        "total_rewards_paid": 1500000,
        "tasks": [
            {"title": "Summarize Wikipedia", "pool_balance": 50000,
             "completion_threshold": 0.95, "best_score": 0.8712,
             "progress": 0.917, "active_miners_24h": 18, "submissions_1h": 56},
            {"title": "Translate EN→FR", "pool_balance": 100000,
             "completion_threshold": 0.90, "best_score": 0.7800,
             "progress": 0.867, "active_miners_24h": 24, "submissions_1h": 72},
        ],
    })

    # Stats
    print_stats(
        {"address": "0x1234567890abcdef1234567890abcdef12345678", "balance": 15650},
        {"pool_reward": 12650, "completion_reward": 3000},
        improvements=8,
    )

    # Balance (inline preview since it's in cli.py)
    from rich.panel import Panel
    from rich.table import Table
    from axon.theme import GOLD, PRIMARY_BOX

    kv = Table(box=None, show_header=False, padding=(0, 2))
    kv.add_column("Key", style="secondary")
    kv.add_column("Value")
    kv.add_row("Wallet", "[address]0x1234567890abcdef1234567890abcdef12345678[/]")
    kv.add_row("USDC", "[money.bold]$156.50[/]  [secondary](platform)[/]")
    kv.add_row("", "")
    kv.add_row("Base Chain", "")
    kv.add_row("  ETH", "0.042000")
    kv.add_row("  USDC", "89.50")
    kv.add_row("  USDT", "0.00")
    panel = Panel(kv, title=branded_title("Balance"), box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2))
    console.print()
    console.print(panel)
    console.print()

    console.print("[brand]── Preview Complete ──[/]\n")


if __name__ == "__main__":
    main()
