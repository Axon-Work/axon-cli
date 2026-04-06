import pytest
import httpx
from eth_account import Account
from eth_account.messages import encode_defunct


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """HTTP client pointing at a running backend on :8000."""
    transport = httpx.AsyncHTTPTransport(proxy=None)
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30, transport=transport) as c:
        yield c


async def _wallet_auth(client: httpx.AsyncClient) -> tuple[str, str]:
    """Create a random wallet, authenticate via nonce/verify, return (token, address)."""
    acct = Account.create()
    address = acct.address.lower()

    # Step 1: get nonce
    resp = await client.get(f"/api/auth/nonce?address={address}")
    assert resp.status_code == 200, f"nonce failed: {resp.text}"
    nonce = resp.json()["nonce"]

    # Step 2: sign & verify
    message = encode_defunct(text=f"Sign in to Axon: {nonce}")
    sig = acct.sign_message(message)
    resp = await client.post("/api/auth/verify", json={
        "address": address,
        "signature": sig.signature.hex(),
    })
    assert resp.status_code == 200, f"verify failed: {resp.text}"
    token = resp.json()["access_token"]
    return token, address


@pytest.fixture
async def publisher_token(client):
    token, _ = await _wallet_auth(client)
    return token


@pytest.fixture
async def miner_token(client):
    token, _ = await _wallet_auth(client)
    return token
