"""Fetch available models from LLM provider APIs."""
import httpx


def fetch_models(provider: str, api_key: str, api_base: str = "") -> list[dict]:
    """Fetch models from provider. Returns list of {label, value}."""
    try:
        if provider == "anthropic" and api_key:
            resp = httpx.get("https://api.anthropic.com/v1/models", headers={
                "x-api-key": api_key, "anthropic-version": "2023-06-01",
            }, timeout=10)
            if resp.status_code == 200:
                models = [m["id"] for m in resp.json().get("data", [])]
                models = [m for m in models if "claude-2" not in m and "instant" not in m]
                models.sort(reverse=True)
                return [{"label": m, "value": f"anthropic/{m}"} for m in models]

        if provider == "openai" and api_key:
            resp = httpx.get("https://api.openai.com/v1/models", headers={
                "Authorization": f"Bearer {api_key}",
            }, timeout=10)
            if resp.status_code == 200:
                prefixes = ("gpt-", "o1", "o3", "o4", "gpt4", "gpt5", "chatgpt")
                models = [m["id"] for m in resp.json().get("data", []) if m["id"].startswith(prefixes)]
                models.sort(reverse=True)
                return [{"label": m, "value": f"openai/{m}"} for m in models]

        if provider == "deepseek" and api_key:
            resp = httpx.get("https://api.deepseek.com/v1/models", headers={
                "Authorization": f"Bearer {api_key}",
            }, timeout=10)
            if resp.status_code == 200:
                models = sorted(m["id"] for m in resp.json().get("data", []))
                return [{"label": m, "value": f"deepseek/{m}"} for m in models]

        if provider == "ollama":
            base = api_base or "http://localhost:11434"
            resp = httpx.get(f"{base}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = sorted(m["name"] for m in resp.json().get("models", []))
                return [{"label": m, "value": f"ollama/{m}"} for m in models]
    except Exception:
        pass
    return []
