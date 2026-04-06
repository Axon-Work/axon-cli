"""Backend HTTP client with automatic wallet auth."""
import httpx
from axon.config import load_config, get_token, save_config


def _ensure_auth():
    """Auto-authenticate with wallet if no valid token."""
    transport = httpx.HTTPTransport(proxy=None)

    token = get_token()
    if token:
        config = load_config()
        try:
            with httpx.Client(base_url=config["server_url"], timeout=5, transport=transport) as c:
                resp = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 200:
                return  # Token still valid
        except httpx.ConnectError:
            raise
        except Exception:
            pass  # Token expired or invalid, try re-auth below

    # Token missing or expired — re-auth with wallet
    from axon.wallet import load_wallet, sign_message
    wallet = load_wallet()
    if not wallet:
        return

    config = load_config()
    with httpx.Client(base_url=config["server_url"], timeout=10, transport=transport) as c:
        # Get nonce
        resp = c.get(f"/api/auth/nonce?address={wallet['address']}")
        if resp.status_code != 200:
            return
        nonce_data = resp.json()

        # Sign
        signature = sign_message(nonce_data["message"], wallet["private_key"])

        # Verify
        resp = c.post("/api/auth/verify", json={
            "address": wallet["address"],
            "signature": signature,
        })
        if resp.status_code == 200:
            save_config({"auth_token": resp.json()["access_token"]})


def _client(auth: bool = True, timeout: int = 120) -> httpx.Client:
    if auth:
        _ensure_auth()
    config = load_config()
    headers = {"Content-Type": "application/json"}
    token = get_token()
    if auth and token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(
        base_url=config["server_url"],
        headers=headers,
        timeout=timeout,
        transport=httpx.HTTPTransport(proxy=None),
    )


def api_get(path: str, auth: bool = True) -> dict | list:
    with _client(auth=auth) as c:
        resp = c.get(path)
        resp.raise_for_status()
        return resp.json()


def api_post(path: str, body: dict, auth: bool = True) -> dict:
    with _client(auth=auth) as c:
        resp = c.post(path, json=body)
        resp.raise_for_status()
        return resp.json()


def api_patch(path: str, body: dict | None = None, auth: bool = True) -> dict:
    with _client(auth=auth) as c:
        resp = c.patch(path, json=body) if body else c.patch(path)
        resp.raise_for_status()
        return resp.json()
