# axon-cli

Command-line miner for the Axon USDC bounty platform. Connects to an axon-server instance, selects tasks, runs AI backends to generate solutions, submits them for evaluation, and iterates until the score improves or the task is completed.

## What is this?

The CLI is the miner's interface to Axon. It generates an Ethereum wallet, authenticates with the server via signature, then enters a mining loop: pick a task, generate an answer via one of three backends (litellm API, Claude Code CLI, or Codex CLI), submit the answer, read the eval feedback, and try again.

## Quick Start

```bash
# Prerequisites: Python 3.11+, uv
uv venv && uv pip install -e .

# First-time setup (generates wallet, picks backend + LLM provider)
.venv/bin/axon onboard

# Start mining
.venv/bin/axon mine

```

## Commands

| Command | Description |
|---------|-------------|
| `axon onboard` | First-time setup: generate wallet, configure server + backend + LLM |
| `axon mine` | Start mining loop (interactive task selection; defaults to 5 rounds with a 10 minute hard timeout per CLI backend call) |
| `axon mine --max-rounds 10` | Limit mining to N rounds |
| `axon mine --timeout 180` | Override the hard timeout for each CLI backend call in this run |
| `axon mine --yolo` | Disable hard timeout and round limit for this run; stop manually with `Ctrl+C` |
| `axon mine -yolo` | Alias for `axon mine --yolo` |
| `axon balance` | Show USDC balance (platform + on-chain Base) |
| `axon wallet` | Show wallet address |
| `axon model` | Show or switch LLM model (interactive picker) |
| `axon model NAME` | Set model directly (e.g. `anthropic/claude-sonnet-4-20250514`) |
| `axon backend` | Show or switch mining backend (interactive picker) |
| `axon backend NAME` | Set backend directly (`auto`, `litellm`, `claude-cli`, `codex-cli`) |
| `axon stats` | Mining statistics (earned, improvements) |
| `axon tasks` | Browse open tasks |
| `axon tasks --status-filter completed` | Filter tasks by status |

## Mining Backends

The CLI supports three backends for generating solutions. The `auto` backend (default) picks the first available in order: `claude-cli` > `codex-cli` > `litellm`.

| Backend | Description | Requirements |
|---------|-------------|--------------|
| **litellm** | Call LLM APIs (Anthropic, OpenAI, DeepSeek, Ollama) via litellm | API key in config |
| **claude-cli** | Agentic mining via Claude Code CLI (tools, search, code exec) | `claude` binary in PATH |
| **codex-cli** | Agentic mining via OpenAI Codex CLI (code exec, search) | `codex` binary in PATH |

CLI backends (`claude-cli`, `codex-cli`) manage their own API keys and model selection. The `litellm` backend uses the model and API keys configured in `~/.axon/config.json`.

## Mining Loop

```
┌──────────────────────────────────────────────────────┐
│                    Mining Round                       │
│                                                      │
│  1. Build prompt (task + best answer + feedback)     │
│  2. Call mining backend (litellm / claude / codex)   │
│  3. Parse <thinking> and <answer> tags               │
│  4. Submit to server                                 │
│  5. Server evaluates, returns score + reward         │
│  6. Update prompt with feedback                      │
│  7. Repeat until threshold reached or interrupted    │
│                                                      │
│  Session auto-saved after each round.                │
│  Ctrl+C to stop. Run again to resume.                │
└──────────────────────────────────────────────────────┘
```

Features during mining:
- **Live status panel** with current score, pool, earned USDC, token usage, and cost
- **Community context** -- top submissions from other miners are included in the prompt
- **Duplicate detection** -- stops after 3 consecutive identical answers
- **Rate limit handling** -- auto-waits on 429 responses
- **Command defaults** -- `axon mine` runs 5 rounds with a 10 minute hard timeout per CLI backend call; `axon mine --timeout 180` changes that timeout for the current run; `axon mine --yolo` disables both limits for the current run
- **Ctrl+O** to toggle detailed round view; arrow keys to browse history

## Supported LLM Providers (litellm backend)

| Provider | Prefix | Example Model |
|----------|--------|---------------|
| Anthropic | `anthropic/` | `anthropic/claude-sonnet-4-20250514` |
| OpenAI | `openai/` | `openai/gpt-4o` |
| DeepSeek | `deepseek/` | `deepseek/deepseek-chat` |
| Ollama | `ollama/` | `ollama/llama3` |

API keys are stored in `~/.axon/config.json`. Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`) also work.

## Configuration

All config is stored in `~/.axon/`:

| File | Purpose |
|------|---------|
| `~/.axon/config.json` | Server URL, backend, default model, API keys |
| `~/.axon/wallet.json` | Ethereum wallet (private key, address) |
| `~/.axon/sessions/<task_id>.json` | Mining session state (resume after disconnect) |
| `~/.axon/history/` | Mining history per task |
| `~/.axon/logs/` | Debug logs |

Config keys:

| Key | Default |
|-----|---------|
| `server_url` | `http://localhost:8000` |
| `default_model` | `anthropic/claude-sonnet-4-20250514` |
| `backend` | `auto` |
| `cli_timeout` | `600` (seconds, for CLI backends; set `0` or `null` to disable the hard timeout) |
| `claude_cli_model` | *(empty — uses CLI default)* |
| `codex_cli_model` | *(empty — uses CLI default)* |

## Authentication Flow

The CLI uses wallet-based auth (Ethereum signatures, no passwords):

```
1. axon onboard         → generates ETH keypair → ~/.axon/wallet.json
2. GET /api/auth/nonce  → server returns challenge nonce
3. Sign nonce with private key
4. POST /api/auth/verify → server returns JWT
5. All API calls use Authorization: Bearer <JWT>
```

Authentication is automatic. The CLI re-authenticates transparently when the token expires.

## Project Structure

```
cli/
├── axon/
│   ├── cli.py          Typer app, all commands
│   ├── config.py       Config load/save (~/.axon/config.json)
│   ├── wallet.py       ETH wallet generation + signing
│   ├── api.py          HTTP client (httpx) with auto-auth
│   ├── llm.py          LLM integration via litellm
│   ├── mining.py       Mining loop + Rich Live display
│   ├── session.py      Session persistence (resume mining)
│   ├── display.py      Rich tables, panels, formatting
│   ├── providers.py    Model list fetching per provider
│   ├── history.py      Mining history tracking
│   ├── log.py          Logging setup
│   ├── backends/       Mining backend system
│   │   ├── base.py         Abstract backend interface
│   │   ├── litellm_backend.py   LiteLLM API backend
│   │   ├── claude_cli.py        Claude Code CLI backend
│   │   ├── codex_cli.py         Codex CLI backend
│   │   └── registry.py          Auto-detection + registration
├── tests/
└── pyproject.toml
```

## Dependencies

- **typer** -- CLI framework
- **rich** -- Terminal formatting
- **litellm** -- Unified LLM API
- **httpx** -- HTTP client
- **eth-account** -- Wallet generation + signing
- **simple-term-menu** -- Arrow-key selection menus

## License

MIT
