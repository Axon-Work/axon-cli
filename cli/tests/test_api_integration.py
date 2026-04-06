"""Integration tests for CLI → API auth flow. Requires backend on :8000."""
import pytest
from axon.wallet import generate_wallet, save_wallet
from axon.config import save_config, load_config


@pytest.fixture(autouse=True)
def _use_tmp_axon_dir(tmp_path, monkeypatch):
    """Redirect ~/.axon to a temp dir so tests don't touch real config."""
    axon_dir = tmp_path / ".axon"
    axon_dir.mkdir()
    monkeypatch.setattr("axon.config.CONFIG_DIR", axon_dir)
    monkeypatch.setattr("axon.config.CONFIG_FILE", axon_dir / "config.json")
    monkeypatch.setattr("axon.wallet.WALLET_FILE", axon_dir / "wallet.json")
    save_config({"server_url": "http://localhost:8000"})


def test_ensure_auth_full_flow():
    """_ensure_auth should auto-authenticate with a fresh wallet against a running server."""
    from axon.api import _ensure_auth
    from axon.config import get_token

    # Generate and save a wallet
    wallet = generate_wallet()
    save_wallet(wallet)

    # No token yet
    assert get_token() == ""

    # This should: get nonce → sign → verify → save token
    _ensure_auth()

    # Token should now be saved
    token = get_token()
    assert token != ""
    assert len(token) > 20


def test_api_get_me():
    """api_get('/api/auth/me') should return user profile after auto-auth."""
    from axon.api import api_get

    wallet = generate_wallet()
    save_wallet(wallet)

    me = api_get("/api/auth/me")
    assert me["address"] == wallet["address"].lower()
    assert "balance" in me


def test_api_get_tasks_no_auth():
    """api_get with auth=False should work without wallet."""
    from axon.api import api_get

    tasks = api_get("/api/tasks?task_status=open", auth=False)
    assert isinstance(tasks, list)
