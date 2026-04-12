import json
import os
from pathlib import Path

AXON_HOME = Path(os.environ.get("AXON_HOME", str(Path.home() / ".axon")))
CONFIG_DIR = AXON_HOME
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "auth_token": "",
    "default_model": "anthropic/claude-sonnet-4-20250514",
    "api_base": "",
    "api_keys": {},
    "backend": "auto",
    "cli_timeout": 600,
    "claude_cli_model": "",
    "codex_cli_model": "",
}


def resolve_cli_timeout(config: dict, default: int = 600) -> int | None:
    """Return CLI backend timeout in seconds, or None when disabled."""
    raw_timeout = config.get("cli_timeout", default)
    if raw_timeout is None:
        return None
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        return default
    return None if timeout <= 0 else timeout


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {**DEFAULT_CONFIG}
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return {**DEFAULT_CONFIG, **data, "api_keys": {**DEFAULT_CONFIG["api_keys"], **data.get("api_keys", {})}}
    except Exception:
        return {**DEFAULT_CONFIG}


def save_config(updates: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = load_config()
    if "api_keys" in updates:
        current["api_keys"] = {**current.get("api_keys", {}), **updates.pop("api_keys")}
    current.update(updates)
    CONFIG_FILE.write_text(json.dumps(current, indent=2) + "\n")


def get_token() -> str:
    config = load_config()
    return config.get("auth_token", "")
