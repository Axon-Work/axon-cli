import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".axon"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "auth_token": "",
    "default_model": "anthropic/claude-sonnet-4-20250514",
    "api_base": "",
    "api_keys": {},
}


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
