"""Axon CLI entry point."""
import json
import os
import subprocess
import tempfile
from typing import Optional
import httpx
import typer
from axon.api import api_get, api_post, api_patch
from axon.theme import console, branded_title, GOLD, PRIMARY_BOX
from axon.display import print_banner, _fmt_usdc
from axon.log import setup_logging

setup_logging()

app = typer.Typer(name="axon", help="Axon — USDC Bounty Mining CLI", add_completion=False)


def _api(fn, *args, **kwargs):
    """Call an API function with unified error handling."""
    try:
        return fn(*args, **kwargs)
    except httpx.ConnectError:
        console.print("[error]Cannot connect to server. Is the backend running?[/]")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            console.print("[error]Not authenticated. Run: [command]axon onboard[/][/]")
        else:
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            console.print(f"[error]Error {e.response.status_code}: {detail or e}[/]")
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
            console.print("First time? Run [command]axon onboard[/] to get started.\n")
            console.print("  [command]axon onboard[/]       Generate wallet + setup")
            console.print("  [command]axon tasks[/]         List available tasks")
            console.print("  [command]axon mine[/]          Start mining a task")
            console.print("  [command]axon --help[/]        All commands")
        else:
            from axon.wallet import get_address
            from axon.config import load_config
            config = load_config()
            addr = get_address()
            model = config.get("default_model", "not set")
            console.print(f"  wallet: [address]{addr[:6]}...{addr[-4:]}[/]  model: [accent]{model}[/]\n")
            console.print("  [command]axon tasks[/]         List available tasks")
            console.print("  [command]axon task <id>[/]     View task details")
            console.print("  [command]axon mine[/]          Start mining a task")
            console.print("  [command]axon balance[/]       Check USDC balance")
            console.print("  [command]axon wallet[/]        Show wallet address")


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


def _select_param(title: str, options: list[str], values: list, custom_prompt: str, custom_type: type):
    """Preset selection menu with Custom fallback. Returns value or raises typer.Exit."""
    idx = _select(title, options)
    if idx is None:
        raise typer.Exit()
    value = values[idx]
    if value is None:  # Custom
        return typer.prompt(f"  {custom_prompt}", type=custom_type)
    return value


@app.command()
def onboard():
    """First-time setup — generate wallet, configure model."""
    from axon.config import save_config
    from axon.wallet import load_wallet, generate_wallet, save_wallet

    console.print(f"\n{branded_title('Onboard')}\n")

    # Step 1: Wallet
    existing_wallet = load_wallet()
    if existing_wallet:
        console.print(f"  Wallet exists: [address]{existing_wallet['address']}[/]")
        if not typer.confirm("Generate a new wallet? (this will replace the existing one)", default=False):
            console.print("  [success]✓ Keeping existing wallet[/]")
        else:
            wallet = generate_wallet()
            save_wallet(wallet)
            console.print(f"  [success]✓ New wallet: {wallet['address']}[/]")
    else:
        wallet = generate_wallet()
        save_wallet(wallet)
        console.print(f"  [success]✓ Wallet generated: {wallet['address']}[/]")
        console.print(f"  [secondary]Private key saved to ~/.axon/wallet.json[/]")

    # Step 2: Connect & authenticate with server
    console.print()
    from axon.config import load_config, DEFAULT_CONFIG
    save_config({"server_url": DEFAULT_CONFIG["server_url"]})
    server = load_config()["server_url"]
    try:
        with httpx.Client(timeout=5, transport=httpx.HTTPTransport(proxy=None)) as c:
            resp = c.get(f"{server}/health")
        if resp.status_code == 200:
            console.print(f"  [success]✓ Connected to server[/]")
        else:
            console.print(f"  [error]✗ Server returned {resp.status_code}[/]")
    except Exception:
        console.print(f"  [warning]⚠ Cannot reach server[/]")
    try:
        from axon.api import _ensure_auth
        _ensure_auth()
        console.print("  [success]✓ Authenticated[/]")
    except Exception:
        console.print("  [warning]⚠ Could not authenticate (server may be offline)[/]")

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
            avail = " [error](not installed)[/]"
        elif bid == "codex-cli" and not shutil.which("codex"):
            avail = " [error](not installed)[/]"
        backend_labels.append(f"{label}{avail}")

    idx = _select("  Select mining backend:\n", backend_labels)
    if idx is None:
        idx = 0
    chosen_backend = backend_list[idx][0]
    save_config({"backend": chosen_backend})
    console.print(f"  [success]✓ Backend: {chosen_backend}[/]")
    _check_cli_available(chosen_backend, shutil)

    # CLI backends skip API key / model selection
    if chosen_backend in ("claude-cli", "codex-cli"):
        console.print(f"\n  [secondary]Using {chosen_backend} — API keys and model managed by the CLI tool.[/]")
    else:
        console.print()
        _configure_api_backend()

    # Done
    from axon.wallet import get_address
    console.print(f"\n{branded_title('Setup complete!')}")
    console.print(f"  Wallet: [address]{get_address()}[/]\n")
    console.print("  Run [command]axon tasks[/] to see available tasks.")
    console.print("  Run [command]axon mine[/] to start mining.\n")


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
    console.print(f"  [success]✓ {provider_label}[/]\n")

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
            console.print(f"  Saved key: [secondary]{preview}[/]")
            if not typer.confirm("  Use saved key?", default=True):
                api_key = typer.prompt(f"  Enter {env_var or 'API key'}")
                save_config({"api_keys": {provider: api_key}})
                console.print(f"  [success]✓ Key saved[/]")
            else:
                api_key = saved_key
        elif env_key:
            preview = f"{env_key[:8]}...{env_key[-4:]}"
            console.print(f"  Found [address]{env_var}[/] in environment: [secondary]{preview}[/]")
            if typer.confirm("  Use this key?", default=True):
                api_key = env_key
            else:
                api_key = typer.prompt(f"  Enter {env_var}")
            save_config({"api_keys": {provider: api_key}})
            console.print(f"  [success]✓ Key saved[/]")
        else:
            api_key = typer.prompt(f"  Enter {env_var or 'API key'}")
            save_config({"api_keys": {provider: api_key}})
            console.print(f"  [success]✓ Key saved[/]\n")

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
            console.print(f"  [success]✓ Model: {provider}/{model_name}[/]")
        else:
            save_config({"default_model": models[idx]["value"]})
            console.print(f"  [success]✓ Model: {models[idx]['value']}[/]")
    else:
        console.print("  [warning]Could not fetch models — enter manually[/]")
        model_name = typer.prompt("Model name")
        save_config({"default_model": f"{provider}/{model_name}"})
        console.print(f"  [success]✓ Model: {provider}/{model_name}[/]")


# --- Wallet ---

@app.command()
def wallet():
    """Show wallet address."""
    from axon.wallet import load_wallet
    w = load_wallet()
    if not w:
        console.print("[error]No wallet. Run: axon onboard[/]")
        raise typer.Exit(1)
    console.print(f"  Address: [address]{w['address']}[/]")
    console.print(f"  [secondary]Key file: ~/.axon/wallet.json[/]")


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
        console.print(f"  [success]✓ Model: {name}[/]")
        return

    console.print(f"\n  Current model: [address]{current}[/]\n")

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
        console.print(f"  [success]✓ Model: {name}[/]")
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
            console.print(f"  Using [address]{env_var}[/] from environment")
        else:
            api_key = typer.prompt(f"Enter {env_var or 'API key'}")
            save_config({"api_keys": {provider: api_key}})
            console.print(f"  [success]✓ Key saved[/]")

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
            console.print(f"  [success]✓ Model: {provider}/{name}[/]")
        else:
            save_config({"default_model": models[idx]["value"]})
            console.print(f"  [success]✓ Model: {models[idx]['value']}[/]")
    else:
        console.print("  [warning]Could not fetch models[/]")
        name = typer.prompt("Model name")
        save_config({"default_model": f"{provider}/{name}"})
        console.print(f"  [success]✓ Model: {provider}/{name}[/]")


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
            console.print(f"[error]Unknown backend '{name}'. Choose from: {', '.join(valid)}[/]")
            raise typer.Exit(1)
        if name != "auto":
            _check_cli_available(name, shutil)
        save_config({"backend": name})
        resolved = auto_detect_backend() if name == "auto" else name
        console.print(f"  [success]✓ Backend: {name}[/]" + (f" [secondary](→ {resolved})[/]" if name == "auto" else ""))
        if name == "litellm":
            console.print()
            _configure_api_backend()
        return

    resolved = auto_detect_backend() if current == "auto" else current
    console.print(f"\n  Current backend: [address]{current}[/]" + (f" [secondary](→ {resolved})[/]" if current == "auto" else "") + "\n")

    # Mark availability
    labels = []
    for bid, label in backends:
        avail = ""
        if bid == "claude-cli" and not shutil.which("claude"):
            avail = " [error](not installed)[/]"
        elif bid == "codex-cli" and not shutil.which("codex"):
            avail = " [error](not installed)[/]"
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
    console.print(f"  [success]✓ Backend: {chosen}[/]" + (f" [secondary](→ {resolved})[/]" if chosen == "auto" else ""))

    if chosen == "litellm":
        console.print()
        _configure_api_backend()


def _check_cli_available(backend_name: str, shutil):
    """Warn if CLI tool is not installed."""
    if backend_name == "claude-cli" and not shutil.which("claude"):
        console.print("  [warning]⚠ 'claude' CLI not found in PATH. Install: npm install -g @anthropic-ai/claude-code[/]")
    elif backend_name == "codex-cli" and not shutil.which("codex"):
        console.print("  [warning]⚠ 'codex' CLI not found in PATH. Install: npm install -g @openai/codex[/]")


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
            console.print("[warning]No open tasks.[/]")
            raise typer.Exit(1)
        if idx < 1 or idx > len(task_list):
            console.print(f"[error]Row #{idx} out of range (1-{len(task_list)})[/]")
            raise typer.Exit(1)
        data = task_list[idx - 1]
    else:
        data = _api(api_get, f"/api/tasks/{task_id}", auth=False)

    print_task_detail(data)


# --- Mine (task selection) ---

@app.command()
def mine(
    max_rounds: Optional[int] = typer.Option(
        None,
        "--rounds",
        min=0,
        help="Maximum mining rounds. 0 = unlimited (stop with Ctrl+C).",
    ),
    timeout: Optional[int] = typer.Option(
        None,
        "--timeout",
        min=0,
        help="Hard timeout in seconds for each CLI backend call. 0 = no timeout.",
    ),
    budget: Optional[float] = typer.Option(
        None,
        "--budget",
        min=0,
        help="Spending limit in USD for metered backends. 0 = no limit.",
    ),
):
    """Start mining a task. Runs continuously by default — stop with Ctrl+C."""
    from axon.config import load_config
    from axon.backends import auto_detect_backend
    from axon.mining import run_mining

    # Get open tasks
    task_list = _api(api_get, "/api/tasks?status_filter=open", auth=False)
    if not task_list:
        console.print("[warning]No open tasks available.[/]")
        raise typer.Exit()

    if len(task_list) == 1:
        task = task_list[0]
        console.print(f"  Mining: [brand]{task['title']}[/]  Pool: [money]{_fmt_usdc(task.get('pool_balance', 0))}[/]\n")
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

    # Determine backend type
    config = load_config()
    backend_name = config.get("backend", "auto")
    if backend_name == "auto":
        backend_name = auto_detect_backend()
    is_metered = backend_name not in ("claude-cli", "codex-cli")

    # Interactive preset menus for parameters not passed via CLI flags
    if max_rounds is None:
        max_rounds = _select_param(
            "  ⛏ Rounds:\n",
            ["Unlimited", "5 rounds", "10 rounds", "50 rounds", "Custom..."],
            [0, 5, 10, 50, None],
            "Rounds (0 = unlimited)", int,
        )
    if is_metered and budget is None:
        console.print("  [warning]⚠ Metered backend — API calls will incur costs.[/]")
        budget = _select_param(
            "  💰 Budget:\n",
            ["No limit", "$1.00", "$5.00", "$20.00", "Custom..."],
            [0.0, 1.0, 5.0, 20.0, None],
            "Budget in USD (0 = no limit)", float,
        )
    if budget is None:
        budget = 0.0
    if timeout is None:
        timeout = _select_param(
            "  ⏱ Timeout:\n",
            ["None", "30s", "60s", "120s", "Custom..."],
            [0, 30, 60, 120, None],
            "Timeout per round in sec (0 = none)", int,
        )

    effective_timeout = None if timeout == 0 else timeout
    os.system("clear")
    print_banner()
    run_mining(task, max_rounds, cli_timeout_override=effective_timeout, budget=budget)


# --- Balance ---

@app.command()
def balance():
    """Show USDC balance + on-chain assets (Base)."""
    from rich.panel import Panel
    from rich.table import Table

    me = _api(api_get, "/api/auth/me")
    addr = me["address"]

    kv = Table(box=None, show_header=False, padding=(0, 2))
    kv.add_column("Key", style="secondary")
    kv.add_column("Value")

    kv.add_row("Wallet", f"[address]{addr}[/]")
    kv.add_row("USDC", f"[money.bold]{_fmt_usdc(me['balance'])}[/]  [secondary](platform)[/]")

    # On-chain balances (Base mainnet)
    kv.add_row("", "")
    kv.add_row("Base Chain", "")
    try:
        on_chain = _fetch_base_balances(addr)
        kv.add_row("  ETH", f"{on_chain['eth']:.6f}")
        kv.add_row("  USDC", f"{on_chain['usdc']:.2f}")
        kv.add_row("  USDT", f"{on_chain['usdt']:.2f}")
    except Exception:
        kv.add_row("", "[secondary](could not fetch on-chain balances)[/]")

    panel = Panel(kv, title=branded_title("Balance"), box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2))
    console.print()
    console.print(panel)
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


# --- Publish ---

@app.command()
def publish(file: Optional[str] = typer.Argument(None, help="JSON task config file")):
    """Publish a new task funded from your balance."""
    from rich.panel import Panel
    from rich.table import Table
    from axon.wallet import load_wallet

    # Check wallet
    w = load_wallet()
    if not w:
        console.print("[error]No wallet. Run: [command]axon onboard[/][/]")
        raise typer.Exit(1)

    # Get balance
    me = _api(api_get, "/api/auth/me")
    balance = me["balance"]
    console.print(f"\n  Balance: [money.bold]{_fmt_usdc(balance)}[/]\n")

    if balance <= 0:
        console.print("[error]No balance to fund a task. Top up first.[/]")
        raise typer.Exit(1)

    # Build task data
    if file:
        data = _publish_from_file(file)
    else:
        data = _publish_wizard(balance)

    # Local pre-check: pool > balance
    if data["pool_balance"] > balance:
        console.print(f"[error]Pool {_fmt_usdc(data['pool_balance'])} exceeds balance {_fmt_usdc(balance)}.[/]")
        raise typer.Exit(1)

    # Preview
    _print_publish_preview(data)

    if not typer.confirm("\n  Publish this task?", default=True):
        console.print("  [secondary]Cancelled.[/]")
        raise typer.Exit()

    # Submit
    result = _api(api_post, "/api/tasks/publish", data)
    console.print(f"\n  [success]✓ Task published![/]")
    console.print(f"  ID: [secondary]{result['id']}[/]")
    console.print(f"  Pool: [money]{_fmt_usdc(result['pool_balance'])}[/]")
    console.print(f"  Balance remaining: [money]{_fmt_usdc(balance - data['pool_balance'])}[/]\n")


def _publish_from_file(path: str) -> dict:
    """Read and validate a JSON task config file."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        console.print(f"[error]File not found: {path}[/]")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[error]Invalid JSON: {e}[/]")
        raise typer.Exit(1)

    required = ["title", "description", "eval_type", "eval_config", "completion_threshold", "pool_balance"]
    missing = [f for f in required if f not in data]
    if missing:
        console.print(f"[error]Missing required fields: {', '.join(missing)}[/]")
        raise typer.Exit(1)

    return data


def _publish_wizard(balance: int) -> dict:
    """Interactive task creation wizard."""
    console.print(f"  {branded_title('Publish Task')}\n")

    # Step 1: Eval type
    eval_types = ["code_output", "llm_judge"]
    eval_labels = [
        "code_output  (sandbox code execution + scoring)",
        "llm_judge    (LLM evaluates answer against rubric)",
    ]
    idx = _select("  Eval type:\n", eval_labels)
    if idx is None:
        raise typer.Exit()
    eval_type = eval_types[idx]
    console.print(f"  [success]✓ {eval_type}[/]\n")

    # Step 2: Title
    title = typer.prompt("  Task title")

    # Step 3: Description
    console.print()
    description = _prompt_text("Description")

    # Step 4: Eval config
    console.print()
    if eval_type == "code_output":
        eval_config = _wizard_code_output_config()
    else:
        eval_config = _wizard_llm_judge_config()

    # Step 5: Direction
    console.print()
    dir_labels = ["maximize  (higher score is better)", "minimize  (lower score is better)"]
    idx = _select("  Direction:\n", dir_labels)
    if idx is None:
        raise typer.Exit()
    direction = "maximize" if idx == 0 else "minimize"
    console.print(f"  [success]✓ {direction}[/]\n")

    # Step 6: Completion threshold
    completion_threshold = typer.prompt("  Completion threshold (score)", type=float)

    # Step 7: Pool balance
    console.print()
    pool_balance = _select_pool(balance)

    # Step 8: Completion reward %
    console.print()
    completion_reward_pct = _select_param(
        "  Completion reward %:\n",
        ["50% (default)", "30%", "70%", "Custom..."],
        [50, 30, 70, None],
        "Completion reward % (0-100)", int,
    )

    return {
        "title": title,
        "description": description,
        "eval_type": eval_type,
        "eval_config": eval_config,
        "direction": direction,
        "completion_threshold": completion_threshold,
        "pool_balance": pool_balance,
        "completion_reward_pct": completion_reward_pct,
    }


def _wizard_code_output_config() -> dict:
    """Sub-wizard for code_output eval config."""
    console.print("  [brand]Eval Config: code_output[/]\n")
    setup_code = _prompt_text("Setup code (test harness)")
    config: dict = {"setup_code": setup_code}

    score_prefix = typer.prompt("  Score prefix", default="SCORE:")
    if score_prefix:
        config["score_prefix"] = score_prefix

    timeout = typer.prompt("  Timeout (seconds)", default=30, type=int)
    config["timeout"] = timeout

    gpu_labels = ["None (CPU only)", "T4", "A100", "H100"]
    gpu_values = [None, "T4", "A100", "H100"]
    idx = _select("  GPU:\n", gpu_labels)
    if idx is not None and gpu_values[idx]:
        config["gpu"] = gpu_values[idx]

    return config


def _wizard_llm_judge_config() -> dict:
    """Sub-wizard for llm_judge eval config."""
    console.print("  [brand]Eval Config: llm_judge[/]\n")
    rubric = _prompt_text("Rubric (scoring criteria)")
    config: dict = {"rubric": rubric}

    model = typer.prompt("  Judge model", default="anthropic/claude-sonnet-4-20250514")
    config["model"] = model

    max_score = typer.prompt("  Max score", default=1.0, type=float)
    config["max_score"] = max_score

    return config


def _prompt_text(label: str) -> str:
    """Multi-line text input: file / $EDITOR / inline."""
    options = ["Load from file", "Open in $EDITOR", "Type inline"]
    idx = _select(f"  {label} input method:\n", options)
    if idx is None:
        raise typer.Exit()

    if idx == 0:
        # File
        path = typer.prompt(f"  File path")
        try:
            with open(os.path.expanduser(path)) as f:
                text = f.read()
        except Exception as e:
            console.print(f"[error]Cannot read file: {e}[/]")
            raise typer.Exit(1)
    elif idx == 1:
        # $EDITOR
        text = _open_editor(suffix=".txt")
    else:
        # Inline
        console.print("  [secondary]Enter text (empty line to finish):[/]")
        lines = []
        while True:
            line = input("  ")
            if line == "":
                break
            lines.append(line)
        text = "\n".join(lines)

    if not text.strip():
        console.print(f"[error]{label} cannot be empty.[/]")
        raise typer.Exit(1)

    preview = text.strip()[:80]
    console.print(f"  [success]✓ {label}[/]: [secondary]{preview}{'…' if len(text.strip()) > 80 else ''}[/]\n")
    return text.strip()


def _open_editor(suffix: str = ".txt") -> str:
    """Open $EDITOR with a temp file and return its contents."""
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        tmp_path = f.name

    try:
        subprocess.run([editor, tmp_path], check=True)
        with open(tmp_path) as f:
            return f.read()
    except subprocess.CalledProcessError:
        console.print("[error]Editor exited with error.[/]")
        raise typer.Exit(1)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _select_pool(balance: int) -> int:
    """Pool balance selection with dollar presets."""
    presets = [
        (1000, "$10"),
        (5000, "$50"),
        (10000, "$100"),
        (50000, "$500"),
    ]
    options = []
    values: list[int | None] = []
    for cents, label in presets:
        if cents <= balance:
            options.append(label)
            values.append(cents)
    options.append("Custom...")
    values.append(None)

    idx = _select("  Pool balance (USDC):\n", options)
    if idx is None:
        raise typer.Exit()
    pool = values[idx]
    if pool is None:
        usd = typer.prompt("  Amount in USD", type=float)
        pool = int(usd * 100)
    console.print(f"  [success]✓ Pool: {_fmt_usdc(pool)}[/]\n")
    return pool


def _print_publish_preview(data: dict):
    """Rich panel preview of task to be published."""
    from rich.panel import Panel
    from rich.table import Table

    kv = Table(box=None, show_header=False, padding=(0, 2))
    kv.add_column("Key", style="secondary")
    kv.add_column("Value")

    kv.add_row("Title", data["title"])
    kv.add_row("Eval Type", data["eval_type"])
    kv.add_row("Direction", data.get("direction", "maximize"))
    kv.add_row("Threshold", str(data["completion_threshold"]))
    kv.add_row("Pool", f"[money]{_fmt_usdc(data['pool_balance'])}[/]")
    pct = data.get("completion_reward_pct", 50)
    bonus = (data["pool_balance"] * pct) // 100
    kv.add_row("Completion Reward", f"[money]{_fmt_usdc(bonus)}[/]  [secondary]({pct}%)[/]")

    desc_preview = data["description"][:120]
    if len(data["description"]) > 120:
        desc_preview += "..."
    kv.add_row("Description", f"[secondary]{desc_preview}[/]")

    panel = Panel(kv, title=branded_title("Publish Preview"), box=PRIMARY_BOX, border_style=GOLD, padding=(1, 2))
    console.print()
    console.print(panel)
