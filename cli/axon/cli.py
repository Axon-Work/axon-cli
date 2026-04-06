"""Axon CLI entry point."""
import httpx
import typer
from axon.api import api_get, api_post, api_patch
from axon.display import console
from axon.log import setup_logging

setup_logging()

app = typer.Typer(name="axon", help="Axon — Proof of Useful Work Mining CLI")


def _api(fn, *args, **kwargs):
    """Call an API function with unified error handling."""
    try:
        return fn(*args, **kwargs)
    except httpx.ConnectError:
        console.print("[red]Cannot connect to server. Is the backend running?[/]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            console.print("[red]Not authenticated. Run: axon onboard[/]")
        else:
            console.print(f"[red]Error: {e.response.status_code}[/]")
        raise typer.Exit(1)


def _is_first_run() -> bool:
    from axon.wallet import load_wallet
    return load_wallet() is None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Axon CLI. Run 'axon onboard' for first-time setup."""
    if ctx.invoked_subcommand is None:
        if _is_first_run():
            console.print("[bold gold1]ψ Welcome to Axon![/]\n")
            console.print("First time? Run [bold green]axon onboard[/] to get started.\n")
            console.print("  [green]axon onboard[/]       Generate wallet + setup")
            console.print("  [green]axon mine[/]          Start mining")
            console.print("  [green]axon tui[/]           Interactive dashboard")
            console.print("  [green]axon --help[/]        All commands")
        else:
            from axon.wallet import get_address
            from axon.config import load_config
            config = load_config()
            addr = get_address()
            model = config.get("default_model", "not set")
            console.print(f"[bold gold1]ψ Axon[/]  wallet: [cyan]{addr[:6]}...{addr[-4:]}[/]  model: [cyan]{model}[/]\n")
            console.print("  [green]axon mine[/]          Start mining")
            console.print("  [green]axon tasks list[/]    Browse tasks")
            console.print("  [green]axon balance[/]       Check $AXN balance")
            console.print("  [green]axon tui[/]           Interactive dashboard")
            console.print("  [green]axon wallet[/]        Show wallet address")


# --- Onboard ---

def _select(title: str, options: list[str], cursor_index: int = 0) -> int | None:
    """Arrow-key selection menu. Returns chosen index or None if cancelled."""
    from simple_term_menu import TerminalMenu
    menu = TerminalMenu(
        options,
        title=title,
        cursor_index=cursor_index,
        menu_cursor="  ❯ ",
        menu_cursor_style=("fg_green", "bold"),
        menu_highlight_style=("fg_green", "bold"),
    )
    return menu.show()


@app.command()
def onboard():
    """First-time setup — generate wallet, configure model."""
    from axon.config import save_config
    from axon.wallet import load_wallet, generate_wallet, save_wallet

    console.print("\n[bold gold1]ψ Axon Onboard[/]\n")

    # Step 1: Wallet
    existing_wallet = load_wallet()
    if existing_wallet:
        console.print(f"  Wallet exists: [cyan]{existing_wallet['address']}[/]")
        if not typer.confirm("Generate a new wallet? (this will replace the existing one)", default=False):
            console.print("  [green]✓ Keeping existing wallet[/]")
        else:
            wallet = generate_wallet()
            save_wallet(wallet)
            console.print(f"  [green]✓ New wallet: {wallet['address']}[/]")
    else:
        wallet = generate_wallet()
        save_wallet(wallet)
        console.print(f"  [green]✓ Wallet generated: {wallet['address']}[/]")
        console.print(f"  [dim]Private key saved to ~/.axon/wallet.json[/]")

    # Step 2: Server
    console.print()
    from axon.config import load_config
    existing = load_config()
    default_server = existing.get("server_url", "http://localhost:8000")
    server = typer.prompt("Server URL", default=default_server)
    try:
        resp = httpx.get(f"{server}/health", timeout=5, transport=httpx.HTTPTransport(proxy=None))
        if resp.status_code == 200:
            console.print(f"  [green]✓ Connected to {server}[/]")
        else:
            console.print(f"  [red]✗ Server returned {resp.status_code}[/]")
    except Exception:
        console.print(f"  [yellow]⚠ Cannot reach {server}[/]")
    save_config({"server_url": server})

    # Step 3: Auto-authenticate with server
    console.print()
    try:
        from axon.api import _ensure_auth
        _ensure_auth()
        console.print("  [green]✓ Authenticated with server[/]")
    except Exception:
        console.print("  [yellow]⚠ Could not authenticate (server may be offline)[/]")

    # Step 4: LLM Provider (arrow-key select)
    console.print()
    provider_list = [
        ("anthropic", "Anthropic (Claude)"),
        ("openai",    "OpenAI (GPT / o-series)"),
        ("deepseek",  "DeepSeek (Chat / Reasoner)"),
        ("ollama",    "Ollama (local models)"),
    ]
    idx = _select("  Select LLM provider:\n", [label for _, label in provider_list])
    if idx is None:
        idx = 0
    provider, provider_label = provider_list[idx]
    console.print(f"  [green]✓ {provider_label}[/]\n")

    # Step 5: API Key (visible) + fetch models
    from axon.providers import fetch_models

    if provider != "ollama":
        import os
        env_names = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
        env_key = env_names.get(provider, "")
        existing_key = os.environ.get(env_key, "") if env_key else ""

        if existing_key:
            preview = f"{existing_key[:8]}...{existing_key[-4:]}"
            console.print(f"  Found [cyan]{env_key}[/] in environment: [dim]{preview}[/]")
            if typer.confirm("Use this key?", default=True):
                api_key = existing_key
            else:
                api_key = typer.prompt(f"Enter {env_key}")
        else:
            api_key = typer.prompt(f"Enter {env_key or 'API key'}")

        save_config({"api_keys": {provider: api_key}})
        key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else api_key
        console.print(f"  [green]✓ Key saved[/] [dim]({key_preview})[/]\n")

        console.print("  Fetching models from API...")
        try:
            models = fetch_models(provider, api_key)
        except Exception:
            models = []

        _pick_model(models, provider, save_config)
    else:
        api_base = typer.prompt("Ollama API base", default="http://localhost:11434")
        save_config({"api_base": api_base})

        console.print("  Fetching local models...")
        try:
            models = fetch_models("ollama", "", api_base)
        except Exception:
            models = []

        _pick_model(models, "ollama", save_config)

    # Done — launch TUI
    from axon.wallet import get_address
    console.print(f"\n[bold gold1]ψ Setup complete![/]")
    console.print(f"  Wallet: [cyan]{get_address()}[/]\n")

    console.print("  Launching TUI...\n")
    from axon.tui.app import run_tui
    run_tui()


def _pick_model(models: list[dict], provider: str, save_config):
    """Arrow-key model picker. Falls back to manual input."""
    if models:
        menu_items = [m["label"] for m in models[:20]] + ["Enter model name manually"]
        console.print(f"  Found [bold]{len(models)}[/] models:\n")
        idx = _select("  Select model:\n", menu_items)
        if idx is None:
            idx = 0
        if idx == len(menu_items) - 1:
            # manual entry
            model_name = typer.prompt("Model name")
            save_config({"default_model": f"{provider}/{model_name}"})
            console.print(f"  [green]✓ Model: {provider}/{model_name}[/]")
        else:
            save_config({"default_model": models[idx]["value"]})
            console.print(f"  [green]✓ Model: {models[idx]['value']}[/]")
    else:
        console.print("  [yellow]Could not fetch models — enter manually[/]")
        model_name = typer.prompt("Model name")
        save_config({"default_model": f"{provider}/{model_name}"})
        console.print(f"  [green]✓ Model: {provider}/{model_name}[/]")


# --- Wallet ---

@app.command()
def wallet():
    """Show wallet address."""
    from axon.wallet import load_wallet
    w = load_wallet()
    if not w:
        console.print("[red]No wallet. Run: axon onboard[/]")
        raise typer.Exit(1)
    console.print(f"  Address: [bold cyan]{w['address']}[/]")
    console.print(f"  [dim]Key file: ~/.axon/wallet.json[/]")


# --- Model ---

@app.command()
def model(name: str = ""):
    """Show or switch LLM model."""
    from axon.config import load_config, save_config
    from axon.providers import fetch_models

    config = load_config()
    current = config.get("default_model", "not set")

    if name:
        # Direct set: axon model anthropic/claude-sonnet-4-20250514
        save_config({"default_model": name})
        console.print(f"  [green]✓ Model: {name}[/]")
        return

    console.print(f"\n  Current model: [bold cyan]{current}[/]\n")

    # Detect provider from current model
    provider = current.split("/")[0] if "/" in current else ""
    keys = config.get("api_keys", {})
    api_key = keys.get(provider, "")
    api_base = config.get("api_base", "")

    models = []
    if api_key or provider == "ollama":
        console.print("  Fetching models...")
        models = fetch_models(provider, api_key, api_base)

    if models:
        menu_items = [m["label"] for m in models[:20]] + ["Enter model name manually"]
        idx = _select("  Select model:\n", menu_items)
        if idx is None:
            return
        if idx == len(menu_items) - 1:
            name = typer.prompt("Model name")
            save_config({"default_model": f"{provider}/{name}" if provider else name})
            console.print(f"  [green]✓ Model: {provider}/{name}[/]")
        else:
            save_config({"default_model": models[idx]["value"]})
            console.print(f"  [green]✓ Model: {models[idx]['value']}[/]")
    else:
        name = typer.prompt("Enter model name (e.g. anthropic/claude-sonnet-4-20250514)")
        save_config({"default_model": name})
        console.print(f"  [green]✓ Model: {name}[/]")


# --- TUI ---

@app.command()
def tui():
    """Launch interactive TUI dashboard."""
    from axon.tui.app import run_tui
    run_tui()


@app.command()
def dev():
    """Launch TUI with CSS hot-reload (dev mode)."""
    import os
    os.environ["TEXTUAL"] = "devtools"
    from axon.tui.app import run_tui
    run_tui()


# --- Mine ---

@app.command()
def mine(task_id: str = "", max_rounds: int = 0, auto: bool = False):
    """Start mining. Shows task list to pick from."""
    from axon.mining import run_mining

    tasks = _api(api_get, "/api/tasks?task_status=open", auth=False)
    tasks.sort(key=lambda t: t.get("pool_balance", 0), reverse=True)

    if not tasks:
        console.print("[red]No open tasks available.[/]")
        raise typer.Exit()

    if not task_id:
        if auto:
            task_id = tasks[0]["id"]
        else:
            menu_items = []
            for t in tasks[:20]:
                best = f"{t['best_score']:.2f}" if t.get("best_score") is not None else "  -"
                menu_items.append(f"{t['title'][:40]:<40}  {t['pool_balance']:>6} $AXN  best: {best}")

            console.print("\n  [bold gold1]ψ Open Tasks[/] (sorted by pool)\n")
            idx = _select("  Select task to mine:\n", menu_items)
            if idx is None:
                raise typer.Exit()
            task_id = tasks[idx]["id"]

    # --- Start mining loop ---
    run_mining(task_id, max_rounds)


# --- Balance ---

@app.command()
def balance():
    """Show $AXN balance."""
    me = _api(api_get, "/api/auth/me")
    console.print(f"  Wallet: [cyan]{me['address'][:6]}...{me['address'][-4:]}[/]")
    console.print(f"  Balance: [bold green]{me['balance']:,} $AXN[/]")


# --- Tasks ---

tasks_app = typer.Typer(help="Task management")
app.add_typer(tasks_app, name="tasks")


@tasks_app.command("list")
def tasks_list(status: str = "open"):
    """List tasks as a Rich Table."""
    from axon.display import print_tasks
    data = _api(api_get, f"/api/tasks?task_status={status}", auth=False)
    if not data:
        console.print("[dim]No tasks found.[/]")
        return
    print_tasks(data, title=f"{status.capitalize()} Tasks")


@tasks_app.command("view")
def tasks_view(task_id: str):
    """View task details."""
    from axon.display import print_task_detail
    t = _api(api_get, f"/api/tasks/{task_id}", auth=False)
    print_task_detail(t)


@tasks_app.command("create")
def tasks_create():
    """Interactively create a new task."""
    console.print("\n[bold gold1]ψ Create Task[/]\n")

    title = typer.prompt("Title")
    description = typer.prompt("Description")

    eval_types = ["exact_match", "numeric", "contains", "regex", "code_output", "llm_judge"]
    console.print("\n  Eval types: " + ", ".join(eval_types))
    eval_type = typer.prompt("Eval type", default="exact_match")
    if eval_type not in eval_types:
        console.print(f"[red]Invalid eval type: {eval_type}[/]")
        raise typer.Exit(1)

    direction = typer.prompt("Direction (maximize/minimize)", default="maximize")
    threshold = typer.prompt("Completion threshold", default="1.0", type=float)
    task_burn = typer.prompt("Task burn ($AXN to stake)", type=int)

    eval_config: dict = {}
    if eval_type == "exact_match":
        expected = typer.prompt("Expected answer")
        eval_config["expected"] = expected
    elif eval_type == "regex":
        pattern = typer.prompt("Regex pattern")
        eval_config["pattern"] = pattern
    elif eval_type == "contains":
        substring = typer.prompt("Required substring")
        eval_config["substring"] = substring

    result = _api(api_post, "/api/tasks", {
        "title": title,
        "description": description,
        "eval_type": eval_type,
        "eval_config": eval_config,
        "direction": direction,
        "completion_threshold": threshold,
        "task_burn": task_burn,
    })
    console.print(f"\n  [green]✓ Task created: {result['id']}[/]")
    console.print(f"  Pool: [green]{result['pool_balance']} $AXN[/]")


@tasks_app.command("close")
def tasks_close(task_id: str):
    """Close a task (refunds remaining pool)."""
    result = _api(api_patch, f"/api/tasks/{task_id}")
    console.print(f"  [green]✓ Task closed: {result['id']}[/]")
    console.print(f"  Refunded: [green]{result.get('pool_balance', 0)} $AXN[/]")


# --- Stats ---

@app.command()
def stats():
    """Show mining statistics."""
    from axon.display import print_stats

    me = _api(api_get, "/api/auth/me")
    txns = _api(api_get, "/api/transactions?limit=1000")

    earned = sum(t["amount"] for t in txns if t.get("amount", 0) > 0)
    burned = abs(sum(t["amount"] for t in txns if t.get("amount", 0) < 0))
    improvements = sum(1 for t in txns if t.get("type") == "mining_reward")

    print_stats(me, earned, burned, improvements)
