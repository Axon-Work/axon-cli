"""Axon CLI entry point."""
import os
import httpx
import typer
from axon.api import api_get, api_post, api_patch
from axon.display import console, print_banner, _fmt_usdc
from axon.log import setup_logging

setup_logging()

app = typer.Typer(name="axon", help="Axon — USDC Bounty Mining CLI", add_completion=False)
DEFAULT_MINE_ROUNDS = 5
DEFAULT_MINE_TIMEOUT = 600


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
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            console.print(f"[red]Error {e.response.status_code}: {detail or e}[/]")
        raise typer.Exit(1)


def _is_first_run() -> bool:
    from axon.wallet import load_wallet
    return load_wallet() is None


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Axon CLI. Run 'axon onboard' for first-time setup."""
    print_banner()
    if ctx.invoked_subcommand is None:
        if _is_first_run():
            console.print("First time? Run [bold green]axon onboard[/] to get started.\n")
            console.print("  [green]axon onboard[/]       Generate wallet + setup")
            console.print("  [green]axon tasks[/]         List available tasks")
            console.print("  [green]axon mine[/]          Start mining a task")
            console.print("  [green]axon --help[/]        All commands")
        else:
            from axon.wallet import get_address
            from axon.config import load_config
            config = load_config()
            addr = get_address()
            model = config.get("default_model", "not set")
            console.print(f"  wallet: [cyan]{addr[:6]}...{addr[-4:]}[/]  model: [cyan]{model}[/]\n")
            console.print("  [green]axon tasks[/]         List available tasks")
            console.print("  [green]axon task <id>[/]     View task details")
            console.print("  [green]axon mine[/]          Start mining a task")
            console.print("  [green]axon balance[/]       Check USDC balance")
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

    console.print("\n[bold gold1]Onboard[/]\n")

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

    # Step 2: Connect & authenticate with server
    console.print()
    from axon.config import load_config, DEFAULT_CONFIG
    save_config({"server_url": DEFAULT_CONFIG["server_url"]})
    server = load_config()["server_url"]
    try:
        with httpx.Client(timeout=5, transport=httpx.HTTPTransport(proxy=None)) as c:
            resp = c.get(f"{server}/health")
        if resp.status_code == 200:
            console.print(f"  [green]✓ Connected to server[/]")
        else:
            console.print(f"  [red]✗ Server returned {resp.status_code}[/]")
    except Exception:
        console.print(f"  [yellow]⚠ Cannot reach server[/]")
    try:
        from axon.api import _ensure_auth
        _ensure_auth()
        console.print("  [green]✓ Authenticated[/]")
    except Exception:
        console.print("  [yellow]⚠ Could not authenticate (server may be offline)[/]")

    # Step 4: Mining backend
    import shutil
    console.print()
    backend_list = [
        ("litellm",    "API (Anthropic / OpenAI / DeepSeek / Ollama)"),
        ("claude-cli", "Claude Code CLI (agentic — tools, search, code exec)"),
        ("codex-cli",  "OpenAI Codex CLI (agentic — code exec, search)"),
    ]
    backend_labels = []
    for bid, label in backend_list:
        avail = ""
        if bid == "claude-cli" and not shutil.which("claude"):
            avail = " [red](not installed)[/]"
        elif bid == "codex-cli" and not shutil.which("codex"):
            avail = " [red](not installed)[/]"
        backend_labels.append(f"{label}{avail}")

    idx = _select("  Select mining backend:\n", backend_labels)
    if idx is None:
        idx = 0
    chosen_backend = backend_list[idx][0]
    save_config({"backend": chosen_backend})
    console.print(f"  [green]✓ Backend: {chosen_backend}[/]")
    _check_cli_available(chosen_backend, shutil)

    # CLI backends skip API key / model selection
    if chosen_backend in ("claude-cli", "codex-cli"):
        console.print(f"\n  [dim]Using {chosen_backend} — API keys and model managed by the CLI tool.[/]")
    else:
        console.print()
        _configure_api_backend()

    # Done
    from axon.wallet import get_address
    console.print(f"\n[bold gold1]ψ Setup complete![/]")
    console.print(f"  Wallet: [cyan]{get_address()}[/]\n")
    console.print("  Run [green]axon tasks[/] to see available tasks.")
    console.print("  Run [green]axon mine[/] to start mining.\n")


def _configure_api_backend():
    """Interactive provider → API key → model selection for API backend."""
    from axon.config import load_config, save_config
    from axon.providers import fetch_models

    config = load_config()

    # Provider selection
    provider_list = [
        ("anthropic", "Anthropic (Claude)"),
        ("openai",    "OpenAI (GPT / o-series)"),
        ("deepseek",  "DeepSeek (Chat / Reasoner)"),
        ("ollama",    "Ollama (local models)"),
    ]
    current_model = config.get("default_model", "")
    current_provider = current_model.split("/")[0] if "/" in current_model else ""
    cursor = next((i for i, (pid, _) in enumerate(provider_list) if pid == current_provider), 0)
    idx = _select("  Select LLM provider:\n", [label for _, label in provider_list], cursor_index=cursor)
    if idx is None:
        return
    provider, provider_label = provider_list[idx]
    console.print(f"  [green]✓ {provider_label}[/]\n")

    # API key
    if provider != "ollama":
        import os
        env_names = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
        env_var = env_names.get(provider, "")
        keys = config.get("api_keys", {})
        saved_key = keys.get(provider, "")
        env_key = os.environ.get(env_var, "") if env_var else ""

        if saved_key:
            preview = f"{saved_key[:8]}...{saved_key[-4:]}" if len(saved_key) > 12 else saved_key
            console.print(f"  Saved key: [dim]{preview}[/]")
            if not typer.confirm("  Use saved key?", default=True):
                api_key = typer.prompt(f"  Enter {env_var or 'API key'}")
                save_config({"api_keys": {provider: api_key}})
                console.print(f"  [green]✓ Key saved[/]")
            else:
                api_key = saved_key
        elif env_key:
            preview = f"{env_key[:8]}...{env_key[-4:]}"
            console.print(f"  Found [cyan]{env_var}[/] in environment: [dim]{preview}[/]")
            if typer.confirm("  Use this key?", default=True):
                api_key = env_key
            else:
                api_key = typer.prompt(f"  Enter {env_var}")
            save_config({"api_keys": {provider: api_key}})
            console.print(f"  [green]✓ Key saved[/]")
        else:
            api_key = typer.prompt(f"  Enter {env_var or 'API key'}")
            save_config({"api_keys": {provider: api_key}})
            console.print(f"  [green]✓ Key saved[/]\n")

        console.print("  Fetching models...")
        try:
            models = fetch_models(provider, api_key)
        except Exception:
            models = []
        _pick_model(models, provider, save_config)
    else:
        api_base = config.get("api_base", "") or "http://localhost:11434"
        api_base = typer.prompt("  Ollama API base", default=api_base)
        save_config({"api_base": api_base})
        console.print("  Fetching local models...")
        try:
            models = fetch_models("ollama", "", api_base)
        except Exception:
            models = []
        _pick_model(models, "ollama", save_config)


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
        save_config({"default_model": name})
        console.print(f"  [green]✓ Model: {name}[/]")
        return

    console.print(f"\n  Current model: [bold cyan]{current}[/]\n")

    # Step 1: Pick provider
    providers = [
        ("anthropic", "Anthropic (Claude)"),
        ("openai",    "OpenAI (GPT / o-series)"),
        ("deepseek",  "DeepSeek (Chat / Reasoner)"),
        ("ollama",    "Ollama (local models)"),
        ("manual",    "Enter model name manually"),
    ]
    current_provider = current.split("/")[0] if "/" in current else ""
    cursor = next((i for i, (pid, _) in enumerate(providers) if pid == current_provider), 0)
    idx = _select("  Select provider:\n", [label for _, label in providers], cursor_index=cursor)
    if idx is None:
        return
    provider, _ = providers[idx]

    if provider == "manual":
        name = typer.prompt("Model name (e.g. anthropic/claude-sonnet-4-20250514)")
        save_config({"default_model": name})
        console.print(f"  [green]✓ Model: {name}[/]")
        return

    # Step 2: Check API key
    keys = config.get("api_keys", {})
    api_key = keys.get(provider, "")
    api_base = config.get("api_base", "")

    if provider != "ollama" and not api_key:
        import os
        env_names = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
        env_var = env_names.get(provider, "")
        env_key = os.environ.get(env_var, "")
        if env_key:
            api_key = env_key
            console.print(f"  Using [cyan]{env_var}[/] from environment")
        else:
            api_key = typer.prompt(f"Enter {env_var or 'API key'}")
            save_config({"api_keys": {provider: api_key}})
            console.print(f"  [green]✓ Key saved[/]")

    # Step 3: Fetch and pick model
    console.print("  Fetching models...")
    try:
        models = fetch_models(provider, api_key, api_base)
    except Exception:
        models = []

    if models:
        menu_items = [m["label"] for m in models[:20]] + ["Enter model name manually"]
        idx = _select("  Select model:\n", menu_items)
        if idx is None:
            return
        if idx == len(menu_items) - 1:
            name = typer.prompt("Model name")
            save_config({"default_model": f"{provider}/{name}"})
            console.print(f"  [green]✓ Model: {provider}/{name}[/]")
        else:
            save_config({"default_model": models[idx]["value"]})
            console.print(f"  [green]✓ Model: {models[idx]['value']}[/]")
    else:
        console.print("  [yellow]Could not fetch models[/]")
        name = typer.prompt("Model name")
        save_config({"default_model": f"{provider}/{name}"})
        console.print(f"  [green]✓ Model: {provider}/{name}[/]")


# --- Backend ---

@app.command()
def backend(name: str = typer.Argument("", help="Backend name: auto, api, claude-cli, codex-cli")):
    """Show or switch mining backend (auto, api, claude-cli, codex-cli)."""
    import shutil
    from axon.backends import auto_detect_backend
    from axon.config import load_config, save_config

    if name == "api":
        name = "litellm"

    config = load_config()
    current = config.get("backend", "auto")

    backends = [
        ("auto",       "Auto (claude-cli > codex-cli > litellm)"),
        ("claude-cli", "Claude Code CLI (agentic — tools, search, code exec)"),
        ("codex-cli",  "OpenAI Codex CLI (agentic — code exec, search)"),
        ("litellm",    "API (Anthropic / OpenAI / DeepSeek / Ollama)"),
    ]

    if name:
        valid = [b[0] for b in backends]
        if name not in valid:
            console.print(f"[red]Unknown backend '{name}'. Choose from: {', '.join(valid)}[/]")
            raise typer.Exit(1)
        if name != "auto":
            _check_cli_available(name, shutil)
        save_config({"backend": name})
        resolved = auto_detect_backend() if name == "auto" else name
        console.print(f"  [green]✓ Backend: {name}[/]" + (f" [dim](→ {resolved})[/]" if name == "auto" else ""))
        if name == "litellm":
            console.print()
            _configure_api_backend()
        return

    resolved = auto_detect_backend() if current == "auto" else current
    console.print(f"\n  Current backend: [bold cyan]{current}[/]" + (f" [dim](→ {resolved})[/]" if current == "auto" else "") + "\n")

    # Mark availability
    labels = []
    for bid, label in backends:
        avail = ""
        if bid == "claude-cli" and not shutil.which("claude"):
            avail = " [red](not installed)[/]"
        elif bid == "codex-cli" and not shutil.which("codex"):
            avail = " [red](not installed)[/]"
        labels.append(f"{label}{avail}")

    cursor = next((i for i, (bid, _) in enumerate(backends) if bid == current), 0)
    idx = _select("  Select mining backend:\n", labels, cursor_index=cursor)
    if idx is None:
        return

    chosen = backends[idx][0]
    if chosen != "auto":
        _check_cli_available(chosen, shutil)
    save_config({"backend": chosen})
    resolved = auto_detect_backend() if chosen == "auto" else chosen
    console.print(f"  [green]✓ Backend: {chosen}[/]" + (f" [dim](→ {resolved})[/]" if chosen == "auto" else ""))

    if chosen == "litellm":
        console.print()
        _configure_api_backend()


def _check_cli_available(backend_name: str, shutil):
    """Warn if CLI tool is not installed."""
    if backend_name == "claude-cli" and not shutil.which("claude"):
        console.print("  [yellow]⚠ 'claude' CLI not found in PATH. Install: npm install -g @anthropic-ai/claude-code[/]")
    elif backend_name == "codex-cli" and not shutil.which("codex"):
        console.print("  [yellow]⚠ 'codex' CLI not found in PATH. Install: npm install -g @openai/codex[/]")


# --- Tasks ---

@app.command()
def tasks(status_filter: str = "open"):
    """List available tasks."""
    from axon.display import print_task_list
    data = _api(api_get, f"/api/tasks?status_filter={status_filter}", auth=False)
    print_task_list(data)


@app.command()
def task(task_id: str):
    """View details of a specific task by ID (or row number from 'axon tasks')."""
    from axon.display import print_task_detail

    # Allow row number shorthand: "axon task 3" → pick 3rd open task
    if task_id.isdigit():
        idx = int(task_id)
        task_list = _api(api_get, "/api/tasks?status_filter=open", auth=False)
        if not task_list:
            console.print("[yellow]No open tasks.[/]")
            raise typer.Exit(1)
        if idx < 1 or idx > len(task_list):
            console.print(f"[red]Row #{idx} out of range (1-{len(task_list)})[/]")
            raise typer.Exit(1)
        data = task_list[idx - 1]
    else:
        data = _api(api_get, f"/api/tasks/{task_id}", auth=False)

    print_task_detail(data)


# --- Mine (task selection) ---

@app.command()
def mine(
    max_rounds: int = typer.Option(
        DEFAULT_MINE_ROUNDS,
        "--max-rounds",
        min=0,
        help="Maximum mining rounds for this run. Use 0 for no round limit.",
    ),
    timeout: int = typer.Option(
        DEFAULT_MINE_TIMEOUT,
        "--timeout",
        min=1,
        help="Hard timeout in seconds for each CLI backend call during this run.",
    ),
    yolo: bool = typer.Option(
        False,
        "--yolo",
        "-yolo",
        help="Disable hard timeout and round limit for this run. Stop with Ctrl+C.",
    ),
):
    """Start mining a task. Select from available tasks."""
    from axon.mining import run_mining

    if yolo and max_rounds != DEFAULT_MINE_ROUNDS:
        console.print("[red]Cannot combine --yolo with --max-rounds.[/]")
        raise typer.Exit(1)
    if yolo and timeout != DEFAULT_MINE_TIMEOUT:
        console.print("[red]Cannot combine --yolo with --timeout.[/]")
        raise typer.Exit(1)

    # Get open tasks
    task_list = _api(api_get, "/api/tasks?status_filter=open", auth=False)
    if not task_list:
        console.print("[yellow]No open tasks available.[/]")
        raise typer.Exit()

    if len(task_list) == 1:
        task = task_list[0]
        console.print(f"  Mining: [bold]{task['title']}[/]  Pool: [green]{_fmt_usdc(task.get('pool_balance', 0))}[/]\n")
    else:
        # Task selection menu
        options = []
        for t in task_list:
            pool = _fmt_usdc(t.get("pool_balance", 0))
            options.append(f"{t['title']}  ({pool})")
        idx = _select("  Select task to mine:\n", options)
        if idx is None:
            return
        task = task_list[idx]

    effective_max_rounds = 0 if yolo else max_rounds
    effective_timeout = None if yolo else timeout
    os.system("clear")
    print_banner()
    run_mining(task, effective_max_rounds, cli_timeout_override=effective_timeout)


# --- Balance ---

@app.command()
def balance():
    """Show USDC balance + on-chain assets (Base)."""
    me = _api(api_get, "/api/auth/me")
    addr = me["address"]
    console.print(f"\n  Wallet:  [cyan]{addr}[/]")
    console.print(f"  USDC:    [bold green]{_fmt_usdc(me['balance'])}[/]  (platform)")

    # On-chain balances (Base mainnet)
    console.print(f"\n  [bold]Base Chain[/]")
    try:
        on_chain = _fetch_base_balances(addr)
        console.print(f"  ETH:     [bold]{on_chain['eth']:.6f}[/]")
        console.print(f"  USDC:    [bold]{on_chain['usdc']:.2f}[/]")
        console.print(f"  USDT:    [bold]{on_chain['usdt']:.2f}[/]")
    except Exception:
        console.print(f"  [dim](could not fetch on-chain balances)[/]")
    console.print()


def _fetch_base_balances(address: str) -> dict:
    """Fetch ETH, USDC, USDT balances on Base mainnet via public RPC."""
    import httpx

    rpcs = [
        "https://base.llamarpc.com",
        "https://base-mainnet.public.blastapi.io",
        "https://mainnet.base.org",
    ]
    usdc_contract = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    usdt_contract = "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2"

    padded_addr = "0" * 24 + address[2:].lower()
    calldata = "0x70a08231" + padded_addr

    def rpc_call(method, params):
        for rpc in rpcs:
            try:
                resp = httpx.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                                  timeout=10, transport=httpx.HTTPTransport(proxy=None))
                result = resp.json().get("result")
                if result:
                    return result
            except Exception:
                continue
        return "0x0"

    eth_raw = rpc_call("eth_getBalance", [address, "latest"])
    usdc_raw = rpc_call("eth_call", [{"to": usdc_contract, "data": calldata}, "latest"])
    usdt_raw = rpc_call("eth_call", [{"to": usdt_contract, "data": calldata}, "latest"])

    return {
        "eth": int(eth_raw, 16) / 1e18,
        "usdc": int(usdc_raw, 16) / 1e6,
        "usdt": int(usdt_raw, 16) / 1e6,
    }


# --- Network ---

@app.command()
def network():
    """Show global network overview — active miners, pools, per-task competition."""
    from axon.display import print_network
    data = _api(api_get, "/api/network", auth=False)
    print_network(data)


# --- Stats ---

@app.command()
def stats():
    """Show mining statistics."""
    from axon.display import print_stats

    me = _api(api_get, "/api/auth/me")
    txns = _api(api_get, "/api/transactions?limit=1000")

    breakdown = {
        "pool_reward": 0,
        "completion_reward": 0,
    }
    for t in txns:
        typ = t.get("type", "")
        amt = t.get("amount", 0)
        if typ in breakdown:
            breakdown[typ] += amt
        elif amt > 0:
            breakdown.setdefault("other_in", 0)
            breakdown["other_in"] = breakdown.get("other_in", 0) + amt

    improvements = sum(1 for t in txns if t.get("type") == "pool_reward")
    print_stats(me, breakdown, improvements)
